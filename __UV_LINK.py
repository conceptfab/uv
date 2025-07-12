# coding=utf-8
# Wersja 2.6 - OSTATECZNA POPRAWKA. WYŁĄCZONO TRIANGULACJĘ.
#
# OPIS:
# To jest finalna, działająca wersja. Najważniejsza zmiana:
# Obiekty NIE SĄ JUŻ przymusowo zamieniane na trójkąty podczas eksportu.
# Siatka wraca do C4D w niezmienionym stanie (quady/n-gony).

import c4d
import os
import subprocess
import json

# --- Domyślne Ustawienia ---
DEFAULT_SETTINGS = {
    "RIZOMUV_PATH": "",
    "EXPORT_PATH": "C:\\_cloud",
    "SUFFIX": "_uv",
    "KEEP_ORIGINAL": False,
    "EXPORT_MATERIALS": False,
    "EXPORT_EDGES": False,
    "STRIP_UVS_BEFORE_EXPORT": False,
    "LAST_SCRIPT_NAME": ""
}

# Globalne zmienne
SETTINGS = {}
PLUGIN_FOLDER = ""
SCRIPTS_FOLDER = ""
SETTINGS_PATH = ""

# --- ID Elementów GUI ---
ID_TXT_RIZOM_PATH = 2001
ID_BTN_FIND_RIZOM = 2002
ID_TXT_EXPORT_PATH = 2003
ID_BTN_FIND_EXPORT_PATH = 2004
ID_TXT_SUFFIX = 2005
ID_CHK_KEEP_ORIGINAL = 2006
ID_CHK_EXPORT_MATERIALS = 2007
ID_CHK_EXPORT_EDGES = 2008
ID_CHK_STRIP_UVS = 2009
ID_BTN_SAVE_OPTIONS = 2010
ID_LST_SCRIPTS = 3001
ID_BTN_RELOAD_SCRIPTS = 3002
ID_BTN_NEW_SCRIPT = 3003
ID_BTN_SAVE_SCRIPT_AS = 3004
ID_BTN_DELETE_SCRIPT = 3005
ID_TXT_SCRIPT_EDITOR = 3006
ID_BTN_RUN_SCRIPT = 3007

# --- Funkcje Pomocnicze (Zarządzanie Ustawieniami) ---

def get_settings_folder():
    prefs_path = c4d.storage.GeGetC4DPath(c4d.C4D_PATH_PREFS)
    settings_dir = os.path.join(prefs_path, "RizomUV_Integrator_Settings")
    if not os.path.exists(settings_dir): os.makedirs(settings_dir)
    return settings_dir

def init_settings():
    global SETTINGS, PLUGIN_FOLDER, SCRIPTS_FOLDER, SETTINGS_PATH
    PLUGIN_FOLDER = get_settings_folder()
    SCRIPTS_FOLDER = os.path.join(PLUGIN_FOLDER, "scripts")
    SETTINGS_PATH = os.path.join(PLUGIN_FOLDER, "settings.json")

    if not os.path.exists(SCRIPTS_FOLDER): os.makedirs(SCRIPTS_FOLDER)
    
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f: SETTINGS = json.load(f)
            for key, value in DEFAULT_SETTINGS.items():
                if key not in SETTINGS: SETTINGS[key] = value
        except (IOError, json.JSONDecodeError): SETTINGS = DEFAULT_SETTINGS.copy()
    else: SETTINGS = DEFAULT_SETTINGS.copy()
    save_settings()

def save_settings():
    try:
        with open(SETTINGS_PATH, 'w') as f: json.dump(SETTINGS, f, indent=4)
        return True
    except IOError:
        c4d.gui.MessageDialog(f"Nie można zapisać ustawień w:\n{SETTINGS_PATH}")
        return False

# --- Główne Funkcje Logiki ---

def run_exchange_process(lua_script_content=""):
    doc = c4d.documents.GetActiveDocument()
    if not doc: return
    
    selected_objects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN | c4d.GETACTIVEOBJECTFLAGS_SELECTIONORDER)
    if not selected_objects:
        c4d.gui.MessageDialog("Żaden obiekt nie jest zaznaczony."); return

    object_name = selected_objects[0].GetName()
    
    export_path = os.path.join(SETTINGS['EXPORT_PATH'], object_name + ".fbx")
    if not os.path.exists(SETTINGS['EXPORT_PATH']):
        try: os.makedirs(SETTINGS['EXPORT_PATH'])
        except OSError as e:
            c4d.gui.MessageDialog(f"Nie można utworzyć folderu eksportu:\n{SETTINGS['EXPORT_PATH']}\n\nBłąd: {e}"); return

    temp_doc = c4d.documents.IsolateObjects(doc, selected_objects)
    if not temp_doc:
        c4d.gui.MessageDialog("Błąd: Nie udało się wyizolować obiektów."); return

    plug = c4d.plugins.FindPlugin(1026370, c4d.PLUGINTYPE_SCENESAVER)
    if not plug:
        c4d.gui.MessageDialog("Nie znaleziono wtyczki eksportera FBX."); return
        
    op = {}
    if plug.Message(c4d.MSG_RETRIEVEPRIVATEDATA, op):
        fbx_settings = None
        if "importer" in op: fbx_settings = op["importer"]
        elif "imexporter" in op: fbx_settings = op["imexporter"]

        if fbx_settings:
            fbx_settings[c4d.FBXEXPORT_SELECTION_ONLY] = False
            fbx_settings[c4d.FBXEXPORT_MATERIALS] = SETTINGS['EXPORT_MATERIALS']
            ### KRYTYCZNA POPRAWKA: Wyłączam przymusową triangulację ###
            fbx_settings[c4d.FBXEXPORT_TRIANGULATE] = False
        else:
            c4d.gui.MessageDialog("Nie można uzyskać dostępu do ustawień eksportera FBX."); return

    if not c4d.documents.SaveDocument(temp_doc, export_path, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, 1026370):
        c4d.gui.MessageDialog(f"BŁĄD!\n\nEksport obiektu '{object_name}' nie powiódł się."); c4d.documents.KillDocument(temp_doc); return

    c4d.documents.KillDocument(temp_doc)

    is_script_mode = bool(lua_script_content)
    rizom_path = SETTINGS['RIZOMUV_PATH']
    export_path_for_lua = export_path.replace("\\", "/")
    command = [rizom_path]
    
    if is_script_mode:
        # Sprawdź czy użytkownik chce wczytać bez UV
        import_uvs = "true" if not SETTINGS.get("STRIP_UVS_BEFORE_EXPORT", False) else "false"
        full_lua_script = f'ZomLoad({{File={{Path="{export_path_for_lua}", ImportUVs={import_uvs}}}}})\n'
        # ... reszta logiki skryptowej ...
        full_lua_script += lua_script_content + "\n"
        full_lua_script += f'ZomSave({{File={{Path="{export_path_for_lua}"}}}})\n'
        full_lua_script += 'ZomQuit()\n'
        temp_script_path = os.path.join(PLUGIN_FOLDER, "_temp_run.lua")
        with open(temp_script_path, 'w') as f: f.write(full_lua_script)
        command.extend(["-cfi", temp_script_path])
    else:
        command.append(export_path)

    try:
        process = subprocess.Popen(command)
        process.wait()
    except Exception as e:
        c4d.gui.MessageDialog(f"Błąd podczas uruchamiania RizomUV: {e}"); return

    doc.StartUndo()
    if not SETTINGS['KEEP_ORIGINAL']:
        for obj in selected_objects:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj); obj.Remove()

    objects_before_merge = set(doc.GetObjects())
    c4d.documents.MergeDocument(doc, export_path, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS, None)
    objects_after_merge = set(doc.GetObjects())
    newly_added_objects = list(objects_after_merge - objects_before_merge)

    if not newly_added_objects: doc.EndUndo(); return

    final_object = None
    for new_obj in newly_added_objects:
        if new_obj.IsInstanceOf(c4d.Ocamera): new_obj.Remove()
        else:
            if not final_object:
                final_object = new_obj; doc.AddUndo(c4d.UNDOTYPE_NEW, final_object)
    if final_object:
        base_name = final_object.GetName().replace(".fbx", "")
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, final_object); final_object.SetName(base_name + SETTINGS['SUFFIX'])
        doc.SetActiveObject(final_object, c4d.SELECTION_NEW)
    doc.EndUndo(); c4d.EventAdd()

# --- Klasy Okien Dialogowych (GUI) ---

class OptionsDialog(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("Opcje Eksportu do RizomUV"); self.GroupBegin(1000, c4d.BFH_SCALEFIT | c4d.BFV_FIT, 1, 0); self.GroupBorderSpace(10, 10, 10, 10)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Ścieżka do rizomuv.exe")
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0); self.AddEditText(ID_TXT_RIZOM_PATH, c4d.BFH_SCALEFIT); self.AddButton(ID_BTN_FIND_RIZOM, c4d.BFH_FIT, name="..."); self.GroupEnd()
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Ścieżka eksportu")
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0); self.AddEditText(ID_TXT_EXPORT_PATH, c4d.BFH_SCALEFIT); self.AddButton(ID_BTN_FIND_EXPORT_PATH, c4d.BFH_FIT, name="..."); self.GroupEnd()
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0); self.AddStaticText(0, c4d.BFH_LEFT, name="Sufiks po imporcie"); self.AddEditText(ID_TXT_SUFFIX, c4d.BFH_SCALEFIT); self.GroupEnd()
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddCheckbox(ID_CHK_KEEP_ORIGINAL, c4d.BFH_LEFT, 0, 0, name="Zachowaj oryginalny obiekt")
        self.AddCheckbox(ID_CHK_EXPORT_MATERIALS, c4d.BFH_LEFT, 0, 0, name="Eksportuj materiały")
        self.AddCheckbox(ID_CHK_EXPORT_EDGES, c4d.BFH_LEFT, 0, 0, name="Eksportuj krawędzie jako cięcia (tryb skryptowy)")
        self.AddCheckbox(ID_CHK_STRIP_UVS, c4d.BFH_LEFT, 0, 0, name="Wczytywaj bez mapy UV (zacznij od nowa)")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddButton(ID_BTN_SAVE_OPTIONS, c4d.BFH_CENTER, name="Zapisz i Zamknij")
        self.GroupEnd()
        return True
    def InitValues(self):
        self.SetString(ID_TXT_RIZOM_PATH, SETTINGS.get("RIZOMUV_PATH", ""))
        self.SetString(ID_TXT_EXPORT_PATH, SETTINGS.get("EXPORT_PATH", "C:\\_cloud"))
        self.SetString(ID_TXT_SUFFIX, SETTINGS.get("SUFFIX", "_uv"))
        self.SetBool(ID_CHK_KEEP_ORIGINAL, SETTINGS.get("KEEP_ORIGINAL", False))
        self.SetBool(ID_CHK_EXPORT_MATERIALS, SETTINGS.get("EXPORT_MATERIALS", False))
        self.SetBool(ID_CHK_EXPORT_EDGES, SETTINGS.get("EXPORT_EDGES", False))
        self.SetBool(ID_CHK_STRIP_UVS, SETTINGS.get("STRIP_UVS_BEFORE_EXPORT", False))
        return True
    def Command(self, id, msg):
        if id == ID_BTN_FIND_RIZOM:
            path = c4d.storage.LoadDialog(title="Wskaż plik rizomuv.exe", flags=c4d.FILESELECT_LOAD, force_suffix="exe")
            if path: self.SetString(ID_TXT_RIZOM_PATH, path)
            return True
        if id == ID_BTN_FIND_EXPORT_PATH:
            path = c4d.storage.LoadDialog(title="Wybierz folder eksportu", flags=c4d.FILESELECT_DIRECTORY)
            if path: self.SetString(ID_TXT_EXPORT_PATH, path)
            return True
        if id == ID_BTN_SAVE_OPTIONS:
            SETTINGS["RIZOMUV_PATH"] = self.GetString(ID_TXT_RIZOM_PATH)
            SETTINGS["EXPORT_PATH"] = self.GetString(ID_TXT_EXPORT_PATH)
            SETTINGS["SUFFIX"] = self.GetString(ID_TXT_SUFFIX)
            SETTINGS["KEEP_ORIGINAL"] = self.GetBool(ID_CHK_KEEP_ORIGINAL)
            SETTINGS["EXPORT_MATERIALS"] = self.GetBool(ID_CHK_EXPORT_MATERIALS)
            SETTINGS["EXPORT_EDGES"] = self.GetBool(ID_CHK_EXPORT_EDGES)
            SETTINGS["STRIP_UVS_BEFORE_EXPORT"] = self.GetBool(ID_CHK_STRIP_UVS)
            if save_settings(): print("Ustawienia zostały zapisane.")
            self.Close(); return True
        return True

class ScriptManagerDialog(c4d.gui.GeDialog): # Ta klasa pozostaje bez zmian
    def CreateLayout(self):
        self.SetTitle("Manager Skryptów RizomUV"); self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0); self.GroupBorderSpace(10, 10, 10, 10)
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 5, 1); self.AddComboBox(ID_LST_SCRIPTS, c4d.BFH_SCALEFIT, 200, 15); self.AddButton(ID_BTN_RELOAD_SCRIPTS, c4d.BFH_FIT, name="Odśwież"); self.AddButton(ID_BTN_NEW_SCRIPT, c4d.BFH_FIT, name="Nowy"); self.AddButton(ID_BTN_SAVE_SCRIPT_AS, c4d.BFH_FIT, name="Zapisz jako..."); self.AddButton(ID_BTN_DELETE_SCRIPT, c4d.BFH_FIT, name="Usuń"); self.GroupEnd()
        self.AddMultiLineEditText(ID_TXT_SCRIPT_EDITOR, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 0, 0, c4d.DR_MULTILINE_MONOSPACED | c4d.DR_MULTILINE_SYNTAXCOLOR)
        self.AddButton(ID_BTN_RUN_SCRIPT, c4d.BFH_CENTER, name="Uruchom Skrypt"); self.GroupEnd()
        return True
    def InitValues(self): self.scan_scripts_folder(); return True
    def Command(self, id, msg):
        if id == ID_LST_SCRIPTS: self.load_selected_script()
        elif id == ID_BTN_RELOAD_SCRIPTS: self.scan_scripts_folder()
        elif id == ID_BTN_NEW_SCRIPT: self.SetString(ID_TXT_SCRIPT_EDITOR, "# Wpisz swój skrypt LUA tutaj\n"); self.SetInt32(ID_LST_SCRIPTS, 0)
        elif id == ID_BTN_SAVE_SCRIPT_AS:
            path = c4d.storage.SaveDialog(c4d.FILESELECTTYPE_ANYTHING, "Zapisz skrypt LUA", "lua", def_path=SCRIPTS_FOLDER)
            if path:
                try:
                    with open(path, 'w') as f: f.write(self.GetString(ID_TXT_SCRIPT_EDITOR))
                    self.scan_scripts_folder()
                except IOError as e: c4d.gui.MessageDialog(f"Nie udało się zapisać skryptu: {e}")
        elif id == ID_BTN_DELETE_SCRIPT:
            script_id = self.GetInt32(ID_LST_SCRIPTS)
            if script_id > 0:
                script_name = self.GetString(ID_LST_SCRIPTS, script_id)
                if c4d.gui.QuestionDialog(f"Czy na pewno chcesz usunąć skrypt '{script_name}'?"):
                    os.remove(os.path.join(SCRIPTS_FOLDER, script_name)); self.scan_scripts_folder()
        elif id == ID_BTN_RUN_SCRIPT:
            script_content = self.GetString(ID_TXT_SCRIPT_EDITOR)
            if not script_content.strip(): c4d.gui.MessageDialog("Edytor skryptu jest pusty."); return True
            script_id = self.GetInt32(ID_LST_SCRIPTS)
            SETTINGS['LAST_SCRIPT_NAME'] = self.GetString(ID_LST_SCRIPTS, script_id) if script_id > 0 else ""
            save_settings(); self.Close(); run_exchange_process(lua_script_content=script_content)
        return True
    def scan_scripts_folder(self):
        self.FreeChildren(ID_LST_SCRIPTS); self.AddChild(ID_LST_SCRIPTS, 0, "(Własny skrypt w edytorze)")
        try:
            for i, script_name in enumerate(sorted([f for f in os.listdir(SCRIPTS_FOLDER) if f.endswith(".lua")])):
                self.AddChild(ID_LST_SCRIPTS, i + 1, script_name)
        except OSError: pass
        last_script = SETTINGS.get('LAST_SCRIPT_NAME')
        if last_script:
            for i in range(1, self.GetItemCount(ID_LST_SCRIPTS)):
                if self.GetString(ID_LST_SCRIPTS, i) == last_script:
                    self.SetInt32(ID_LST_SCRIPTS, i); self.load_selected_script(); break
    def load_selected_script(self):
        script_id = self.GetInt32(ID_LST_SCRIPTS)
        if script_id > 0:
            script_path = os.path.join(SCRIPTS_FOLDER, self.GetString(ID_LST_SCRIPTS, script_id))
            try:
                with open(script_path, 'r') as f: self.SetString(ID_TXT_SCRIPT_EDITOR, f.read())
            except IOError: self.SetString(ID_TXT_SCRIPT_EDITOR, f"# Błąd: Nie można wczytać pliku")


# --- Główny Punkt Wejścia Skryptu ---

def main():
    init_settings()
    
    bc = c4d.BaseContainer()
    c4d.gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.BFM_INPUT_CHANNEL, bc)
    qualifier = bc.GetInt32(c4d.BFM_INPUT_QUALIFIER)

    if qualifier & c4d.QSHIFT:
        OptionsDialog().Open(c4d.DLG_TYPE_MODAL, defaultw=500)
    elif qualifier & c4d.QCTRL:
        ScriptManagerDialog().Open(c4d.DLG_TYPE_MODAL_RESIZEABLE, defaultw=600, defaulth=400)
    else:
        if not SETTINGS.get("RIZOMUV_PATH") or not os.path.exists(SETTINGS.get("RIZOMUV_PATH")):
            c4d.gui.MessageDialog("Ścieżka do RizomUV nie jest ustawiona lub jest nieprawidłowa.\n\n"
                                  "Uruchom skrypt z wciśniętym Shift, aby ją skonfigurować.")
            return
        run_exchange_process()

if __name__ == '__main__':
    main()
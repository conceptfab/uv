# filename: C4D_RizomUV_AutoLink.py

import c4d
import os
import subprocess
import time

# --- Import z biblioteki RizomUV Link ---
# Upewnij się, że pliki RizomUVLinkBase.py oraz folder 'win' z rizomuvlink.pyd
# znajdują się w folderze skryptów Cinema 4D.
try:
    from RizomUVLinkBase import CRizomUVLinkBase, CZEx
except ImportError:
    # Ten blok nie jest konieczny, jeśli pliki są na miejscu, ale pomaga w diagnozie.
    c4d.gui.MessageDialog(
        "Błąd krytyczny: Nie można zaimportować biblioteki RizomUVLink.\n\n"
        "Upewnij się, że pliki 'RizomUVLinkBase.py' oraz 'win/rizomuvlink.pyd' "
        "znajdują się w folderze skryptów Cinema 4D."
    )
    # Zatrzymujemy skrypt, jeśli import się nie powiódł
    raise

# --- Stałe konfiguracyjne ---
# Zaktualizowana ścieżka do programu RizomUV
RIZOMUV_PATH = r"S:\_software\RizomUV\RizomUV 2024.1\rizomuv.exe"
EXPORT_DRIVE = "D:\\"
# Sufiks dla nowego obiektu
SUFFIX = "_uv"
CAMERA_TO_DELETE = "CINEMA_4D_Editor"
FBX_EXPORTER_ID = 1026370
# Port dla komunikacji z RizomUV Link
RIZOMUV_PORT = 19730

def main():
    """
    Wersja skryptu wykorzystująca RizomUV Link do pełnej automatyzacji
    procesu tworzenia UV bez interwencji użytkownika.
    """
    print("--- ROZPOCZYNAM PROCES EXPORT -> RIZOMUV (AUTO) -> IMPORT ---")

    # --- Krok 1: Przygotowanie i Eksport (bez zmian) ---
    doc = c4d.documents.GetActiveDocument()
    if not doc: return
    obj = doc.GetActiveObject()
    if not obj:
        c4d.gui.MessageDialog("Żaden obiekt nie jest zaznaczony.")
        return

    object_name = obj.GetName()
    obj.SetEditorMode(c4d.MODE_OFF)
    obj.SetRenderMode(c4d.MODE_OFF)
    c4d.EventAdd()
    export_path = os.path.join(EXPORT_DRIVE, object_name + ".fbx")
    print(f"Ścieżka eksportu: {export_path}")

    print("Izoluję obiekt w nowym, tymczasowym dokumencie...")
    temp_doc = c4d.documents.IsolateObjects(doc, [obj])
    if not temp_doc:
        c4d.gui.MessageDialog("Błąd krytyczny: Nie udało się wyizolować obiektu.")
        return

    print("Zapisuję tymczasowy dokument, używając ostatnich zapamiętanych ustawień FBX...")
    export_result = c4d.documents.SaveDocument(temp_doc, export_path, 0, FBX_EXPORTER_ID)
    c4d.documents.KillDocument(temp_doc)

    if not export_result:
        print("[KRYTYCZNY BŁĄD] Eksport do FBX nie powiódł się!")
        c4d.gui.MessageDialog(f"KRYTYCZNY BŁĄD!\n\nEksport obiektu '{object_name}' nie powiódł się.")
        obj.SetEditorMode(c4d.MODE_UNDEF)
        obj.SetRenderMode(c4d.MODE_UNDEF)
        return

    print("Eksport zakończony pomyślnie.")

    # --- Krok 2: Uruchomienie RizomUV i automatyzacja przez RizomLink ---
    link = None
    process = None
    try:
        # Uruchomienie RizomUV w trybie nasłuchiwania na polecenia
        print(f"\nUruchamiam RizomUV w tle na porcie {RIZOMUV_PORT}...")
        command = [RIZOMUV_PATH, "-scriptingport", str(RIZOMUV_PORT)]
        process = subprocess.Popen(command)

        # Inicjalizacja połączenia
        link = CRizomUVLinkBase()

        # Oczekiwanie na gotowość RizomUV (port musi być otwarty)
        print("Oczekuję na gotowość RizomUV...")
        timeout = 20  # Czekaj maksymalnie 10 sekund
        start_time = time.time()
        while not link.TCPPortIsOpen(RIZOMUV_PORT):
            time.sleep(0.5)
            if time.time() - start_time > timeout:
                raise RuntimeError("Przekroczono limit czasu oczekiwania na RizomUV.")

        # Nawiązanie połączenia
        link.Connect(RIZOMUV_PORT)
        print(">>> Połączono z RizomUV! <<<")
        print(f"Wersja RizomUV: {link.RizomUVVersion()}")

        # Sekwencja poleceń do automatyzacji
        print("\n--- Wykonuję automatyczne operacje UV ---")
        
        # 1. Załaduj plik
        print("1. Ładowanie pliku FBX...")
        link.Load({'File.Path': export_path})

        # 2. Rozwiń siatkę (Unfold)
        # Można dodać parametry, np. {'Iterations': 50} dla lepszej jakości
        print("2. Rozwijanie siatki (Unfold)...")
        link.Unfold({}) 
        
        # 3. Spakuj wyspy (Pack)
        # Ustawiamy podstawowe parametry pakowania.
        # Wartości Padding i Margin są w jednostkach UV (0-1).
        # Dla tekstury 2048px, 8px paddingu to 8/2048 = 0.0039
        map_res = 2048.0
        padding_px = 8.0
        margin_px = 4.0
        
        pack_params = {
            'Translate': True, # To jest kluczowe, aby włączyć pakowanie
            'Global': {
                'MapResolution': int(map_res),
                'PaddingSize': padding_px / map_res,
                'MarginSize': margin_px / map_res
            }
        }
        print(f"3. Pakowanie wysp UV (Pack) z paddingiem {padding_px}px...")
        link.Pack(pack_params)
        
        # 4. Zapisz zmiany do tego samego pliku
        print("4. Zapisywanie zmian...")
        link.Save({'File.Path': export_path})

        print("--- Operacje UV zakończone pomyślnie. ---")

    except (CZEx, Exception) as e:
        error_msg = f"Wystąpił błąd podczas komunikacji z RizomUV:\n\n{e}"
        print(f"[KRYTYCZNY BŁĄD] {error_msg}")
        c4d.gui.MessageDialog(error_msg)
        return
    finally:
        # Zawsze próbuj zamknąć RizomUV, nawet jeśli wystąpił błąd
        if link and link.TCPPortIsOpen(RIZOMUV_PORT):
            print("Zamykam RizomUV...")
            try:
                link.Quit({})
            except CZEx:
                # Czasem rzuca wyjątek, jeśli proces jest już zamykany
                pass
        if process:
             # Upewnij się, że proces jest definitywnie zamknięty
             time.sleep(1) # Daj chwilę na zamknięcie
             if process.poll() is None:
                 print("Wymuszam zamknięcie procesu RizomUV.")
                 process.kill()
        print(">>> RizomUV zamknięty. Wznawiam skrypt w C4D. <<<")


    # --- Krok 3 & 4: Import, czyszczenie i zmiana nazwy (bez zmian) ---
    print("\nImportuję plik z powrotem do sceny...")
    objects_before_merge = set(doc.GetObjects())
    c4d.documents.MergeDocument(doc, export_path, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS)

    print("Przetwarzam zaimportowane obiekty...")
    objects_after_merge = set(doc.GetObjects())
    newly_added_objects = list(objects_after_merge - objects_before_merge)
    target_object = None
    objects_to_delete = []

    for new_obj in newly_added_objects:
        if new_obj.GetName() == CAMERA_TO_DELETE and new_obj.IsInstanceOf(c4d.Ocamera):
            objects_to_delete.append(new_obj)
        elif not new_obj.IsInstanceOf(c4d.Ocamera) and not new_obj.IsInstanceOf(c4d.Olight):
            target_object = new_obj

    for obj_to_del in objects_to_delete:
        obj_to_del.Remove()

    if target_object:
        target_object.SetEditorMode(c4d.MODE_UNDEF)
        target_object.SetRenderMode(c4d.MODE_UNDEF)
        current_name = target_object.GetName()
        if current_name.endswith(".1"): current_name = current_name[:-2]
        new_name = current_name + SUFFIX
        target_object.SetName(new_name)
        doc.SetActiveObject(target_object, c4d.SELECTION_NEW)
        c4d.gui.MessageDialog(f"Proces zakończony pomyślnie.\n\nZmieniono nazwę na: '{new_name}'")
    else:
        c4d.gui.MessageDialog("Scalanie zakończone, ale nie udało się zidentyfikować nowej geometrii.")

    c4d.EventAdd()
    # Czyszczenie tymczasowego pliku
    try:
        os.remove(export_path)
        print(f"Usunięto tymczasowy plik: {export_path}")
    except OSError as e:
        print(f"Nie udało się usunąć pliku tymczasowego: {e}")

    print("\n--- SKRYPT ZAKOŃCZYŁ PRACĘ ---")

if __name__ == '__main__':
    # Sprawdzenie, czy pliki istnieją, zanim rozpocznie się główna funkcja
    rizom_link_base_path = os.path.join(os.path.dirname(__file__), "RizomUVLinkBase.py")
    rizom_link_pyd_path = os.path.join(os.path.dirname(__file__), "win", "rizomuvlink.pyd")

    if not os.path.exists(RIZOMUV_PATH):
        c4d.gui.MessageDialog(f"Nie znaleziono RizomUV.exe w:\n\n{RIZOMUV_PATH}")
    elif not os.path.exists(rizom_link_base_path) or not os.path.exists(rizom_link_pyd_path):
         c4d.gui.MessageDialog(
            "Brak wymaganych plików biblioteki RizomUV Link.\n\n"
            "Upewnij się, że pliki 'RizomUVLinkBase.py' oraz 'win/rizomuvlink.pyd' "
            "znajdują się w tym samym folderze co ten skrypt."
        )
    else:
        main()
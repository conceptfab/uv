# -*- coding: utf-8 -*-
"""
RizomUV Link Plugin dla Cinema 4D
Wersja: ręczna edycja UV w RizomUV

Autor: AI Assistant
Data: 2024
"""

import c4d
import os
import subprocess
import time
from pathlib import Path

# Import biblioteki RizomUV Link
try:
    from RizomUVLinkBase import CRizomUVLinkBase, CZEx
    RIZOM_LINK_AVAILABLE = True
except ImportError:
    RIZOM_LINK_AVAILABLE = False
    print("UWAGA: RizomUVLinkBase.py nie znaleziony - funkcje automatyczne UV niedostępne")

def find_rizomuv_path():
    possible_paths = [
        r"C:\software\RizomUV 2024.1\rizomuv.exe",
        r"C:\Program Files\RizomUV\RizomUV.exe",
        r"C:\Program Files (x86)\RizomUV\RizomUV.exe",
        r"S:\_software\RizomUV\RizomUV 2024.1\rizomuv.exe",
        r"D:\_software\RizomUV\RizomUV 2024.1\rizomuv.exe"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return ""

def export_to_fbx(obj, export_path):
    print(f"Eksport do FBX: {export_path}")
    doc = c4d.documents.GetActiveDocument()
    temp_doc = c4d.documents.IsolateObjects(doc, [obj])
    if not temp_doc:
        raise RuntimeError("Nie udało się wyizolować obiektu")
    if not c4d.documents.SaveDocument(temp_doc, export_path, 0, 1026370):
        c4d.documents.KillDocument(temp_doc)
        raise RuntimeError(f"Eksport do {export_path} nie powiódł się")
    c4d.documents.KillDocument(temp_doc)
    print("Eksport FBX zakończony")
    return True

def open_rizomuv_and_wait(fbx_path):
    rizom_path = find_rizomuv_path()
    if not rizom_path:
        raise RuntimeError("Nie znaleziono RizomUV!")
    print(f"Otwieram RizomUV: {rizom_path}")
    process = subprocess.Popen([rizom_path, fbx_path])
    print("Czekam aż zamkniesz RizomUV...")
    process.wait()
    print("RizomUV zamknięty. Kontynuuję...")

def import_from_fbx(fbx_path, doc):
    objects_before = set(doc.GetObjects())
    c4d.documents.MergeDocument(doc, fbx_path, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS)
    objects_after = set(doc.GetObjects())
    new_objects = list(objects_after - objects_before)
    if not new_objects:
        raise RuntimeError("Nie zaimportowano żadnych obiektów")
    for obj in new_objects[:]:
        if obj.GetType() == c4d.Ocamera or obj.GetName() == "CINEMA_4D_Editor":
            obj.Remove()
            new_objects.remove(obj)
    if new_objects:
        main_obj = new_objects[0]
        original_name = main_obj.GetName()
        if not original_name.endswith("_UV"):
            main_obj.SetName(original_name + "_UV")
    return new_objects

def start_rizomuv_server():
    """Uruchom RizomUV w trybie serwera"""
    rizom_path = find_rizomuv_path()
    if not rizom_path:
        raise RuntimeError("Nie znaleziono RizomUV!")
    
    print(f"Uruchamiam RizomUV serwer: {rizom_path}")
    
    # Spróbuj różne kombinacje parametrów
    server_commands = [
        [rizom_path, "--server", "--port", "8080"],
        [rizom_path, "--server", "8080"],
        [rizom_path, "-server", "-port", "8080"],
        [rizom_path, "-server", "8080"],
        [rizom_path, "--port", "8080"],
        [rizom_path, "-port", "8080"],
        [rizom_path, "--server"],  # Bez portu - może używa domyślnego
        [rizom_path, "-server"]
    ]
    
    process = None
    for cmd in server_commands:
        try:
            print(f"Próbuję: {' '.join(cmd)}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(3)  # Dłuższe czekanie
            
            # Sprawdź czy proces nadal działa
            if process.poll() is None:
                print(f"Serwer uruchomiony: {' '.join(cmd)}")
                break
            else:
                # Sprawdź błędy
                stdout, stderr = process.communicate()
                print(f"Proces zakończony. STDOUT: {stdout.decode()}")
                print(f"STDERR: {stderr.decode()}")
                process = None
        except Exception as e:
            print(f"Błąd z komendą {' '.join(cmd)}: {e}")
            process = None
    
    if not process:
        raise RuntimeError("Nie udało się uruchomić RizomUV z żadną kombinacją parametrów!")
    
    return process

def auto_uv_with_library(fbx_path, output_path):
    """Automatyczne UV używając biblioteki RizomUV Link"""
    if not RIZOM_LINK_AVAILABLE:
        raise RuntimeError("Biblioteka RizomUV Link niedostępna!")
    
    print("Łączę z RizomUV...")
    link = CRizomUVLinkBase()
    
    # Proste sprawdzenie portu 8080
    if not link.TCPPortIsOpen(8080):
        print("RizomUV nie działa. Uruchamiam...")
        rizom_process = start_rizomuv_server()
        time.sleep(5)
    
    # Połącz
    link.Connect(8080)
    
    print("Wczytuję model BEZ UV...")
    result = link.Load({
        "File": {
            "Path": fbx_path,
            "XYZ": True  # IGNORUJE UV
        }
    })
    
    if result != "IMPORT_TASK_SUCCES":
        raise RuntimeError(f"Błąd wczytywania: {result}")
    
    print("Robię automatyczne UV...")
    link.Select({"PrimType": "Edge", "Select": True, "Auto": {"Skeleton": True}})
    link.Cut({"UseSelection": True})
    link.Unfold({"WorkingSet": "Visible"})
    link.Pack({"Translate": True})
    
    result = link.Save({"File": {"Path": output_path}})
    if result != "EXPORT_TASK_SUCCES":
        raise RuntimeError(f"Błąd eksportu: {result}")
    
    print("Automatyczne UV zakończone!")
    return True

def convert_edge_selection_to_seams(fbx_path, output_path, edge_ids=None):
    """Konwertuj edge selection na seams używając biblioteki RizomUV Link"""
    if not RIZOM_LINK_AVAILABLE:
        raise RuntimeError("Biblioteka RizomUV Link niedostępna!")
    
    print("Łączę z RizomUV...")
    link = CRizomUVLinkBase()
    
    if not link.TCPPortIsOpen(8080):
        print("RizomUV nie działa na porcie 8080. Uruchamiam serwer...")
        rizom_process = start_rizomuv_server()
        
        # Sprawdź ponownie
        if not link.TCPPortIsOpen(8080):
            raise RuntimeError("Nie udało się uruchomić RizomUV serwer!")
    
    link.Connect(8080)
    
    print("Wczytuję model...")
    result = link.Load({
        "File": {
            "Path": fbx_path,
            "XYZ": True  # Ignoruj UV
        }
    })
    
    if result != "IMPORT_TASK_SUCCES":
        raise RuntimeError(f"Błąd wczytywania: {result}")
    
    print("Konwertuję edge selection na seams...")
    
    if edge_ids:
        # Użyj konkretnych ID krawędzi
        link.Cut({
            "PrimType": "Edge",
            "IDs": edge_ids
        })
    else:
        # Użyj aktualnej selekcji (jeśli jest)
        link.Cut({
            "PrimType": "Edge",
            "UseSelection": True
        })
    
    print("Seams utworzone. Rozwijam UV...")
    link.Unfold({"WorkingSet": "Visible"})
    link.Pack({"Translate": True})
    
    # Eksport
    result = link.Save({"File": {"Path": output_path}})
    if result != "EXPORT_TASK_SUCCES":
        raise RuntimeError(f"Błąd eksportu: {result}")
    
    print("Konwersja edge selection na seams zakończona!")
    return True

def get_selected_edge_ids(obj):
    """Pobierz ID wybranych krawędzi z obiektu Cinema 4D"""
    if not obj or obj.GetType() != c4d.Opolygon:
        return None
    
    # Sprawdź czy obiekt ma tag Polygon Selection
    tags = obj.GetTags()
    edge_selection = None
    
    for tag in tags:
        if tag.GetType() == c4d.Tpolygonselection:
            # To jest selekcja poligonów, ale możemy użyć krawędzi
            edge_selection = tag
            break
    
    if not edge_selection:
        print("Nie znaleziono selekcji krawędzi")
        return None
    
    # Pobierz selekcję
    selection = edge_selection.GetBaseSelect()
    if not selection:
        return None
    
    # Konwertuj na listę ID
    edge_ids = []
    for i in range(obj.GetPolygonCount() * 4):  # Każdy poligon ma 4 krawędzie
        if selection.IsSelected(i):
            edge_ids.append(i)
    
    print(f"Znaleziono {len(edge_ids)} wybranych krawędzi")
    return edge_ids

def main():
    doc = c4d.documents.GetActiveDocument()
    obj = doc.GetActiveObject()
    if not obj:
        c4d.gui.MessageDialog("Wybierz obiekt do przetworzenia UV")
        return
    if obj.GetType() != c4d.Opolygon:
        c4d.gui.MessageDialog("Wybrany obiekt nie jest poligonem")
        return
    
    # Automatyczny tryb domyślnie
    mode = "auto" if RIZOM_LINK_AVAILABLE else "manual"
    
    try:
        export_dir = os.path.join(os.path.expanduser("~"), "temp_rizomuv")
        os.makedirs(export_dir, exist_ok=True)
        fbx_path = os.path.join(export_dir, f"{obj.GetName()}_temp.fbx")
        output_path = os.path.join(export_dir, f"{obj.GetName()}_output.fbx")
        
        export_to_fbx(obj, fbx_path)
        
        if mode == "auto" and RIZOM_LINK_AVAILABLE:
            # Sprawdź czy użytkownik chce konwersję edge selection
            result = c4d.gui.MessageDialog("Wybierz tryb:\n\nOK - Edge Selection → Seams\nAnuluj - Automatyczne UV", c4d.GEMB_OKCANCEL)
            
            if result == c4d.GEMB_OK:
                # Konwersja edge selection na seams
                edge_ids = get_selected_edge_ids(obj)
                convert_edge_selection_to_seams(fbx_path, output_path, edge_ids)
            else:
                # Automatyczne UV
                auto_uv_with_library(fbx_path, output_path)
            
            new_objects = import_from_fbx(output_path, doc)
        else:
            # Ręczne UV
            open_rizomuv_and_wait(fbx_path)
            new_objects = import_from_fbx(fbx_path, doc)
        
        c4d.EventAdd()
        print(f"Pomyślnie zaimportowano: {new_objects[0].GetName()}")
        c4d.gui.MessageDialog(f"Import zakończony!\nUtworzono: {new_objects[0].GetName()}")
    except Exception as e:
        error_msg = f"Błąd podczas procesu UV:\n{str(e)}"
        print(f"[BŁĄD] {error_msg}")
        c4d.gui.MessageDialog(error_msg)

if __name__ == "__main__":
    main()

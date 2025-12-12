import os
import utils
import time

def run_generator(gen_func, *args):
    """Helper to run a generator and print output to console"""
    print("-" * 50)
    for line in gen_func(*args):
        print(line, end='')
    print("-" * 50)

def main_menu():
    while True:
        print("\n=== Cross-Platform RAM Forensics Tool (CLI) ===")
        print(f"   [Config] Volatility: {'FOUND' if utils.VOL_PATH else 'NOT FOUND'}")
        print(f"   [Config] WinPMEM:    {'FOUND' if utils.WINPMEM_PATH else 'NOT FOUND'}")
        print(f"   [Config] ADB:        {'FOUND' if utils.ADB_PATH else 'NOT FOUND'}")
        print("-----------------------------------------")
        print("1. [Windows] Extract RAM")
        print("2. [Windows] Analyze RAM Dump")
        print("3. [Android] Extract RAM")
        print("4. [Android] Analyze RAM Dump")
        print("5. [Web]     Start Web Interface")
        print("0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "1":
            run_generator(utils.stream_extract_windows)
            
        elif choice == "2":
            file_path = input("Enter filename (e.g. dump.raw): ").strip('"').strip()
            if not os.path.isfile(file_path) and os.path.isfile(file_path + ".raw"):
                file_path += ".raw"
                
            if os.path.exists(file_path):
                run_generator(utils.stream_analyze, file_path, "windows")
            else:
                print("[-] File not found.")
                
        elif choice == "3":
            run_generator(utils.stream_extract_android)
            
        elif choice == "4":
            file_path = input("Enter filename (e.g. dump.raw): ").strip('"').strip()
            if not os.path.isfile(file_path) and os.path.isfile(file_path + ".raw"):
                file_path += ".raw"

            if os.path.exists(file_path):
                run_generator(utils.stream_analyze, file_path, "android")
            else:
                print("[-] File not found.")
        
        elif choice == "5":
            print("[*] Launching Web Interface...")
            os.system("python app.py")

        elif choice == "0":
            print("[*] Exiting...")
            break
        else:
            print("[-] Invalid option.")
        
        time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n[!] User interrupted.")
        sys.exit(0)

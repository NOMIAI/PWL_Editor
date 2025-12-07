import PyInstaller.__main__
import customtkinter
import os
import sys

# Get customtkinter path to include its assets (json themes, etc.)
ctk_path = os.path.dirname(customtkinter.__file__)
print(f"CustomTkinter path found at: {ctk_path}")

# Determine separator for add-data (semicolon for Windows)
sep = ';' if os.name == 'nt' else ':'

# Build arguments
args = [
    'pwl_editor.py',
    '--name=PWL_Editor',
    '--onefile',       # Bundle into a single exe
    '--windowed',      # Do not open a console window
    f'--add-data={ctk_path}{sep}customtkinter', # Include ctk assets
    f'--add-data=icon.png{sep}.',             # Include avatar
    f'--add-data=app_icon.ico{sep}.',         # Include app icon
    '--icon=app_icon.ico',     # Set EXE icon
    '--clean',         # Clean cache
    '--noconfirm',     # Overwrite output directory
    '--hidden-import=customtkinter', # Ensure ctk is imported
    # Exclude heavy libraries not used
    '--exclude-module=matplotlib',
    '--exclude-module=numpy',
    '--exclude-module=pandas',
    '--exclude-module=scipy',
]

print("Starting PyInstaller build with arguments:")
print(args)

PyInstaller.__main__.run(args)

print("\nBuild complete. Check the 'dist' folder for PWL_Editor.exe")

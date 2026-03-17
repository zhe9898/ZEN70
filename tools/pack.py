import os
import zipfile
import fnmatch

def create_zip(source_dir, output_filename):
    # Directories and files to exclude
    excludes = [
        '.git*', 
        'node_modules', 
        '.venv', 
        'venv', 
        '__pycache__', 
        '*.pyc', 
        '.DS_Store', 
        'build_err_invite.txt',
        '*.zip'
    ]

    def should_exclude(path):
        for pattern in excludes:
            if fnmatch.fnmatch(os.path.basename(path), pattern) or \
               any(fnmatch.fnmatch(p, pattern) for p in path.split(os.sep)):
                return True
        return False

    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Modify dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
            
            for file in files:
                file_path = os.path.join(root, file)
                if not should_exclude(file_path):
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
                    print(f"Added: {arcname}")

if __name__ == '__main__':
    source = r"e:\ZEN70"
    output = r"e:\ZEN70\ZEN70_Release_V2.0.zip"
    print(f"Packaging {source} into {output}...")
    create_zip(source, output)
    print("Packaging complete!")
    

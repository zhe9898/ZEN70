import os
import zipfile
import time

def compress_folder(source_folder, output_zip):
    ignore_dirs = {'.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', '.pytest_cache'}
    ignore_files = {'.DS_Store', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'}
    
    print(f"开始打包: {source_folder} -> {output_zip} (V2.1 架构脱敏纯净版)")
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_folder):
            # 原地移除不需要遍历的目录
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                if file in ignore_files or file.endswith('.pyc'):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_folder)
                zipf.write(file_path, arcname)
                
    print(f"打包完成! 文件位置: {output_zip}")

if __name__ == '__main__':
    src = "e:\\新建文件夹"
    dst = "e:\\ZEN70_v2.1_Release.zip"
    compress_folder(src, dst)

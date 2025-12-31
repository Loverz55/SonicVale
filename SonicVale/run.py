# run.py - PyInstaller 打包入口
import os
import sys

# 设置工作目录为 exe 所在目录
if getattr(sys, 'frozen', False):
    # 打包后的 exe 运行
    application_path = os.path.dirname(sys.executable)
    os.chdir(application_path)
    sys.path.insert(0, application_path)
else:
    # 开发环境
    application_path = os.path.dirname(os.path.abspath(__file__))
    os.chdir(application_path)

import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8200)

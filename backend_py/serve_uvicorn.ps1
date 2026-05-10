Set-Location 'D:\relay'
& 'D:\Python\Python3.11.9\python.exe' -m uvicorn backend_py.app:app --host 127.0.0.1 --port 8081

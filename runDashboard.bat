cd D:\Desktop\dev\discordBot-Tueka\dashboard\frontend
npm install
npm run build

cd ..\..
$env:DASHBOARD_UI_V2="true"
.venv\Scripts\python.exe -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000

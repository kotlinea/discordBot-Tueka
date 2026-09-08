# Windowsで動かす

## 準備

Python 3.13とNode.jsをインストールします。仮想環境が削除済みPythonを参照する場合は再作成してください。

```powershell
Remove-Item .venv -Recurse
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`Remove-Item`はプロジェクト直下の`.venv`であることを確認してから実行します。

## 起動

Bot、Dashboard、Workerは別Terminalで起動します。Dashboardだけは`runDashboard.bat`も利用できます。

公開運用ではWindows FirewallとReverse Proxyを設定し、Uvicornの`127.0.0.1:8000`を直接公開しないでください。

## 更新

Processを停止し、バックアップ後に依存関係、Migration、Frontend、Docsの順で更新してから再起動します。[更新とロールバック](./upgrade)も参照してください。

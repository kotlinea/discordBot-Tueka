# 検証環境と依存固定

Phase 0の開発用手順。進捗・実行結果は `PROGRESS0910.md` に記録する。本番運用構成は今後のPhase 3で整備する。

## Python

- 直接依存の制約：`requirements.txt`
- 推移依存・環境Marker・配布物ハッシュ：`requirements.lock`
- 対象：Python 3.13。Lock生成はuv 0.8.22のuniversal resolution。
- テスト用Base Imageは `Dockerfile.test` でdigestを固定する。更新時はLockとテストを再検証する。

```sh
docker build --no-cache -f Dockerfile.test -t tueka-test:p0 .
docker run --rm --network none tueka-test:p0
```

ローカルのPython 3.13仮想環境でも同じLockを使う。

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip check
python -m unittest discover -s tests -p 'test_*.py'
```

依存更新はPython 3.13の隔離環境で行い、生成差分をレビューする。

```sh
python -m pip install uv==0.8.22
uv pip compile requirements.txt --python-version 3.13 --universal --generate-hashes --output-file requirements.lock
```

既存Lockを意図的に更新する場合だけ `--upgrade` を追加する。Linuxで生成できたことだけでWindows実行成功とは判定しない。

## Frontend / Docs

Node 24を使用し、それぞれのディレクトリで `npm ci` を実行する。`npm install` による自動Lock更新をBaseline取得へ混在させない。

Frontendでは `npm run typecheck`、`npm test`、`npm run build`、`npm run test:a11y` を実行する。Docsで `npm run build` 後、Frontendから `npm run test:docs-a11y` を実行する。PlaywrightのChromiumとOS依存が別途必要。

`.dockerignore` は秘密値・DB・Transcript・Backup・ローカル依存と生成物を除外する。コンテナテストへ本番Tokenや本番DBを渡さない。保存先を伴うテストは一時DBを使用する。

Webの全検査を固定Node Imageで実行するには次を使う。

```sh
docker build -f Dockerfile.web-test -t tueka-web-test:p0 .
docker run --name tueka-web-baseline --shm-size=1g tueka-web-test:p0
docker cp tueka-web-baseline:/tmp/tueka-baseline ./baseline
```

`scripts/web-baseline.mjs` は各検査のログ、終了コード、秒数を保存し、失敗があっても後続検査を実行する。最後に失敗の有無を終了コードへ反映する。Node版もsummary.jsonへ保存する。CIでは出力ディレクトリをmountしArtifactへ保存する。

CIのPythonジョブはLinuxとWindowsでPython 3.13の全テストを実行する。コンテナジョブはPythonとWebのbuild・テスト、secretsジョブは固定Gitleaks ImageでGit履歴を検査する。ログへ秘密値を出さないよう `--redact` を必須とする。ローカルの未コミット差分はGit履歴検査に含まれない。

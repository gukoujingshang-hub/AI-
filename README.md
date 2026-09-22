# 日時作業（日報・月次レポート自動化ツール）

日々の作業内容をカレンダーから日報として記録し、月末にはそれらを集計して月報を作成、指定した提出日にはSlackへ自動投稿するためのツールです。

## できること

- カレンダー形式で日付を選び、その日の日報を作成する
- 日報から月報の各項目を自動集計する
- 月報をコピーしたり、GitHub経由でSlackに自動投稿したりする
- 月報の提出日をカレンダー上に赤丸で表示する

## ファイル構成

```
.
├── index.html                          # カレンダーページ（トップページ）
├── report.html                         # 日報作成ページ
├── monthly-report.html                 # 月報作成ページ
├── data/
│   ├── settings.json                   # 月報提出日などの設定（自動生成）
│   └── reports/
│       └── YYYY-MM.json                # 月ごとの月報データ（自動生成）
├── .github/
│   └── workflows/
│       └── post-monthly-report.yml     # 毎日実行され、提出日にSlack投稿するワークフロー
└── scripts/
    └── post_to_slack.py                # 提出日判定・整形・Slack投稿を行うスクリプト
```

`data/` フォルダの中身は最初は存在せず、後述の設定を行うとページから自動で作成・更新されます。

## 使い方の流れ

1. `index.html` を開く（カレンダーが表示される）
2. カレンダー上の日付をクリックすると、その日の日報（`report.html`）が開く
   - 【作業内容】【良かった点・学び】【課題・反省点】【来月の目標・注力事項】【その他】を記入し「保存する」を押す
3. カレンダー右上の「月報作成」ボタンから月報ページ（`monthly-report.html`）を開く
   - 「日報から全項目を自動集計する」を押すと、その月の日報から①〜④の内容を自動で集めてくれる
   - 内容を確認・調整し「コピーする」でクリップボードにコピー、または「保存する」でブラウザに保存できる

## Slackへの自動投稿を使う場合のセットアップ

日々の日報・月報はブラウザの中（localStorage）だけに保存されるため、そのままではSlackへの自動投稿はできません。GitHub Actions（無料の定期実行の仕組み）を使って自動化するには、以下の準備が必要です。

### ① Slack Incoming Webhookを作成する

投稿したいSlackチャンネル用のIncoming Webhookを発行し、URLを控えておく。

### ② GitHubリポジトリにSecretを登録する

このリポジトリの `Settings → Secrets and variables → Actions → New repository secret` から、

- Name: `SLACK_WEBHOOK_URL`
- Value: ①で発行したWebhook URL

を登録する。

### ③ GitHub Personal Access Tokenを発行する

`Settings → Developer settings → Personal access tokens → Fine-grained tokens` から、

- 対象リポジトリ：このリポジトリのみに限定
- 権限：「Contents: Read and write」のみ

を指定したトークンを発行する（他の権限は不要）。

### ④ ページ側でGitHub連携を設定する

`index.html` を開き、上部の「GitHub連携設定」を開いて、GitHubユーザー名・リポジトリ名・③のトークンを入力して保存する。
トークンはブラウザのlocalStorageに保存され、他の場所には送信されない（GitHubへの通信を除く）。共有PCでは利用しないこと。

### ⑤ 月報を作成したらGitHubに同期する

`monthly-report.html` で月報を作成したら、「保存する」に加えて「GitHubに同期する」を押す。
これにより `data/reports/YYYY-MM.json` としてその月の内容（重複整理・日付表記除去済み）がリポジトリに保存される。

### ⑥ 動作確認

リポジトリの「Actions」タブ → `Post Monthly Report to Slack` → 「Run workflow」で手動実行できる。
提出日と一致していれば、その場でSlackに投稿される。

## 自動投稿の仕組み

- 毎日 日本時間9:00（UTC 0:00）に `post-monthly-report.yml` が自動実行される
- `data/settings.json` の提出日と今日の日付が一致するかを確認する
- 一致すればその月の `data/reports/YYYY-MM.json` を読み込み、フォーマットを整えてSlackに投稿する
- 一致しない場合や、提出日なのにその月のデータがまだ無い場合は、投稿の代わりにリマインドメッセージのみ送る

投稿時刻を変更したい場合は `.github/workflows/post-monthly-report.yml` 内の `cron` の値を編集する（UTC基準のため、日本時間から9時間引いた時刻を指定する）。

## 今後の予定

- localStorage依存からの脱却（Flask + SQLiteでの本番運用への移行）
- 半年以上のデータ保持に対応したバックアップ・保存先の見直し

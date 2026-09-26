# VRChat LiveTranslate

[English](README.md) | **繁體中文**

VRChat 即時語音翻譯，使用 Google Gemini Live API。

## 功能

- **我說的話 → VRChat 聊天框。** 用你的語言說話，譯文稍後就會出現在你的聊天框泡泡裡。
- **其他玩家說的話 → 程式視窗。** 遊戲聲音會翻譯成你的語言，顯示在程式的聊天紀錄中。
- **翻譯語音（選用）。** 把你的翻譯語音送進虛擬麥克風，其他玩家就能聽到用他們語言說出的內容。
- **打字訊息。** 在下方輸入框打字後按 Enter，譯文會送到你的聊天框。

程式支援 Windows 10/11。介面提供 English、繁體中文、日本語、한국어。

## 下載與第一次使用

1. 從 [Releases](../../releases/latest) 頁面下載 `LiveTranslate.exe`。單一檔案，免安裝。
2. 雙擊執行。第一次啟動時，介面語言會跟隨 Windows 語言。
3. 開啟 **⚙ 設定**，貼上你的 Gemini API 金鑰（見下一節）。
4. 選擇方向（**我說 / 對方 / 雙向**）與語言，然後按 **開始翻譯**。

如果 Windows 提示缺少 WebView2 Runtime，請到
<https://developer.microsoft.com/microsoft-edge/webview2/> 安裝後再重新啟動程式。

## 取得 Gemini API 金鑰

1. 前往 <https://aistudio.google.com/apikey> 建立金鑰。
2. 在程式中開啟 **⚙ 設定**，貼上金鑰並按 **儲存**。程式會立即檢查金鑰是否可用。

金鑰儲存在 Windows 認證管理員中，不會寫入設定檔或日誌。
也可以改用 `GEMINI_API_KEY` 環境變數。

## VRChat 設定

- 在 VRChat 開啟動作選單 → **Options → OSC → Enabled**。
- 確認聊天框泡泡是可見的（Settings → Chatbox）。

## 翻譯語音設定（選用）

1. 安裝虛擬音訊線：[VB-Cable](https://vb-audio.com/Cable/) 或 VoiceMeeter。
2. 在 VRChat 中，把 **麥克風** 設為虛擬音訊線的輸出端（例如「CABLE Output」）。
3. 在程式中，**麥克風**（⚙ 設定）維持你真正的耳機麥克風，然後開啟 **翻譯語音**。
4. **請戴耳機**，避免程式從喇叭收到遊戲聲音而重複翻譯。

這樣其他玩家只會聽到翻譯，不會聽到你原本的聲音。

**說話聲音**（⚙ 設定）決定翻譯用哪個聲音說出來。「自動」會讓 Gemini 跟隨你自己的聲音；也可以選擇 Gemini 的 30 種
聲音之一（Kore、Puck、Charon…）。想先聽聽差別，可以執行 `python scripts/probe_live.py --voices Kore,Puck`，
再播放它存在 `probe_audio/` 資料夾中的 WAV 檔。

## 設定檔

設定存放在 `%APPDATA%\LiveTranslate\settings.json`，日誌在 `%APPDATA%\LiveTranslate\logs`。
如果想要免安裝的可攜版，在 exe 旁邊放一個名為 `portable.txt` 的空檔案，設定與日誌就會存在 exe 旁邊。
進階數值（模型 ID、語音偵測門檻、聊天框節奏）可以直接在設定檔中修改。

## 疑難排解

| 問題 | 處理方式 |
|---|---|
| 「開始翻譯」按鈕是灰色的 | 到 ⚙ 設定加入 Gemini API 金鑰。 |
| 「Gemini 拒絕了這個 API 金鑰」 | 到 aistudio.google.com 建立新金鑰後重新儲存。 |
| 「已達 Gemini 配額上限」 | 程式會自動重試；稍等一分鐘，或檢查你的 Gemini 配額。 |
| 聊天框沒有出現文字 | 在 VRChat 開啟 OSC，並確認程式中的 **聊天框** 開關已開啟。 |
| 「找不到 VRChat 音訊裝置」 | 播放一些遊戲聲音，檢查設定中的 **VRChat 音訊**，再重新開始。 |
| 「找不到虛擬音訊線」 | 安裝 VB-Cable 或 VoiceMeeter，然後在設定中按 **重新整理**。 |
| 同一句話被翻譯兩次 | 請改用耳機，不要用喇叭。 |
| 其他問題 | ⚙ 設定 → **匯出日誌壓縮檔…**，把 zip 附在問題回報中。API 金鑰已自動移除。 |

## 開發

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]"
.venv/bin/pytest -q                 # Python 測試（離線，不需要音訊裝置）
npm --prefix ui install && npm --prefix ui test
python -m livetranslate --demo      # 示範模式，不需要金鑰或音訊
python -m livetranslate --dev       # 從 `npm --prefix ui run dev` 載入介面
python scripts/probe_live.py        # 用你的金鑰檢查 Gemini Live 模型
python scripts/build.py             # 建置 dist/LiveTranslate.exe（Windows）
```

`python -m livetranslate --self-test [--wav file.wav]` 會把一段錄音送進實際流程，並輸出
`SELFTEST_OK` 或 `SELFTEST_FAIL`。

## 致謝

感謝 [nixi-agent/vrchat-livetranslate](https://github.com/nixi-agent/vrchat-livetranslate) 與
[misyaguziya/VRCT](https://github.com/misyaguziya/VRCT) 帶來的靈感。

## 授權

MIT，詳見 [LICENSE](LICENSE)。

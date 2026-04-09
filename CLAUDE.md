# y-shot 開発ガイドライン

## テストツールとしての設計原則

### DOM直接操作の禁止
y-shotはブラウザ操作の自動化テストツールである。テスト結果の信頼性を担保するため、以下を厳守する。

- `element.checked = true` や `element.value = "..."` のようなDOMプロパティの直接書き換えは禁止
- `dispatchEvent(new Event(...))` による合成イベントの偽造は禁止
- これらは「人間の操作の再現」ではなく「テスト結果の捏造」にあたる

### 許可されるJavaScript実行
- `scrollIntoView()` — スクロール位置の調整（人間もスクロールする）
- `element.click()` — DOM仕様の `HTMLElement.click()` メソッド。セレクタが指す要素（人間が見ている要素）に対してクリックイベントを発火する。label→input の紐づけ等はブラウザが自然に処理する
- 要素情報の取得（読み取り専用のJS実行）

### クリック処理の方針
1. `presence_of_element_located` で要素を取得（サイズゼロやhidden要素でも取得可能）
2. `scrollIntoView` でスクロール
3. `_el.click()` でクリック（Selenium native — 座標ベースで子要素のハンドラも発火する）
4. Selenium clickが `ElementNotInteractableException` で失敗した場合のみ `element.click()` でフォールバック（サイズゼロやhidden要素向け）
5. label→input の紐づけはブラウザに任せる。隠れたinputを探して直接操作してはならない

### やってはいけないこと
- 隠れた `<input>` を探して直接 `input.click()` や `input.checked = true` すること
- `ActionChains` をクリック処理に使うこと（サイズゼロ要素で壊れるため。ホバーには使用可）
- `dispatchEvent` でイベントを偽造すること

## ビルド・リリース

- Python: `C:/Users/2260008/AppData/Local/Python/bin/python.exe` を使用（Windows Store版は不可）
- PyInstallerでexeビルド: `y-shot.spec` / `y-diff.spec`
- リリース: `release/y-shot_vX.X_source/` にソース、`release/y-shot/` にexe

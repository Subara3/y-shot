# y-shot 開発ガイドライン

## テストツールとしての設計原則

### DOM直接操作の禁止
y-shotはブラウザ操作の自動化テストツールである。テスト結果の信頼性を担保するため、以下を厳守する。

- `element.checked = true` や `element.value = "..."` のようなDOMプロパティの直接書き換えは禁止
- `dispatchEvent(new Event(...))` による合成イベントの偽造は禁止
- これらは「人間の操作の再現」ではなく「テスト結果の捏造」にあたる

### 許可されるJavaScript実行
- `scrollIntoView()` — スクロール位置の調整（人間もスクロールする）
- `input.click()` — DOM仕様の `HTMLElement.click()` メソッド。ブラウザがlabelクリック時に内部で実行するのと同じ処理であり、正規のクリックイベントをブラウザの入力処理パイプラインに投入する
- 要素情報の取得（読み取り専用のJS実行）

### クリック処理の方針
1. `element_to_be_clickable` で要素が操作可能になるまで待機
2. `scrollIntoView` + 安定待ち(50ms)
3. `ActionChains.move_to_element().click()` — 人間のマウス操作に最も近い方法
4. labelの場合、for先のinputがuncheckedなら `input.click()` — ブラウザ内部動作の再現
5. フォールバックは設けない。失敗したら素直に失敗させる（テスト結果の再現性を優先）

## ビルド・リリース

- Python: `C:/Users/2260008/AppData/Local/Python/bin/python.exe` を使用（Windows Store版は不可）
- PyInstallerでexeビルド: `y-shot.spec` / `y-diff.spec`
- リリース: `release/y-shot_vX.X_source/` にソース、`release/y-shot/` にexe

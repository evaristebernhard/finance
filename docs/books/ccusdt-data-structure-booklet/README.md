# CCUSDT 数据结构传递小册子

这本小册子解释 CCUSDT replay exchange 中的数据结构如何从市场事件一路传递到 Monitor 页面。

编译：

```powershell
xelatex -interaction=nonstopmode -halt-on-error -jobname=ccusdt-data-structure-booklet-v0_1 -output-directory docs/books/ccusdt-data-structure-booklet/out docs/books/ccusdt-data-structure-booklet/book.tex
xelatex -interaction=nonstopmode -halt-on-error -jobname=ccusdt-data-structure-booklet-v0_1 -output-directory docs/books/ccusdt-data-structure-booklet/out docs/books/ccusdt-data-structure-booklet/book.tex
Copy-Item docs/books/ccusdt-data-structure-booklet/out/ccusdt-data-structure-booklet-v0_1.pdf docs/books/ccusdt-data-structure-booklet/out/ccusdt-data-structure-booklet-v0.1.pdf -Force
```

输出：

```text
docs/books/ccusdt-data-structure-booklet/out/ccusdt-data-structure-booklet-v0.1.pdf
```

边界：

- 不修改 Runner、Bot、diagnostics、monitor 代码。
- 不读取 `date/` 作为 runtime 解释来源。
- 样例只引用已有 run 的关键字段，不复制完整大日志。

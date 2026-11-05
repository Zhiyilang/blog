# 零依赖 Python 实战：我在 UiBot 里做了一套 Excel 自动化组件（全部可复现）

> 文中三个组件均为真实开源项目，纯 Python 标准库实现，共 17 项单元测试全绿：
> [uibot_excel_recon](https://gitee.com/ZhiYIlang/uibot_excel_recon)（6 项）·
> [excel_merge_kit](https://gitee.com/ZhiYIlang/excel_merge_kit)（5 项）·
> [excel_pivot_kit](https://gitee.com/ZhiYIlang/excel_pivot_kit)（6 项）

## 起因：一个真实的需求

做 RPA 的应该都遇到过这个场景：业务部门丢来两个 Excel，"帮我们对一下哪几行不一样"。
需求听起来 trivial，真做起来全是坑：

- 一个是 `.xlsx`，一个是 `.csv`，编码还带 BOM；
- 主键列叫"订单号"，另一个表叫"订单编号"；
- 金额 200 和 200.0 算不算一致？
- 对完还要出一份"哪几行只在这边有"的差异表，业务要拿它去追责。

在 UiBot 里用原生指令当然能做，但流程会拖得很长，而且换个场景又要重画一遍。
所以我用 **纯标准库 Python** 写了三个组件，UiBot 里直接调函数，**不装 openpyxl、不装 pandas**。

## 为什么坚持"零依赖"

这是最实际的一个决定。RPA 机器上的环境你控制不了：

- 公司电脑可能没网，`pip install` 直接失败；
- 装了 pandas，版本和 UiBot 内置的 Python 冲突，一 import 整个流程崩；
- 交付给客户的机器人，多一个第三方库就多一个审计问题。

纯标准库的代价是：**xlsx 得自己解析**。但其实没那么可怕——xlsx 本质是个 zip，里面是 XML。

### 读 xlsx：30 行的最小实现

```python
import zipfile, xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

def read_xlsx(path):
    """把 .xlsx 读成 [[单元格字符串, ...], ...]，不做类型推断。"""
    with zipfile.ZipFile(path) as z:
        # 共享字符串表：Excel 把重复文本集中存放，单元格里只存索引
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
        # 找到第一个工作表
        sheet = next(n for n in z.namelist()
                     if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        root = ET.fromstring(z.read(sheet))
        rows = []
        for row in root.iter(f"{NS}row"):
            cells = {}
            for c in row.findall(f"{NS}c"):
                ref = c.get("r", "")            # 例如 "B3"
                col = "".join(ch for ch in ref if ch.isalpha())
                v = c.find(f"{NS}v")
                if v is None:
                    val = ""
                elif c.get("t") == "s":        # 共享字符串索引
                    val = shared[int(v.text)]
                else:
                    val = v.text or ""
                cells[col] = val
            rows.append(cells)
    return rows
```

三个必须处理的点，漏一个就会读到错数据：

1. **共享字符串表**（`sharedStrings.xml`）—— 不处理的话文本列全变成数字索引；
2. **列字母转序号** —— `B3` 的 `B` 要转成 2，且空单元格不能占位错位；
3. **`t="s"` 属性** —— 区分"这是共享字符串索引"和"这是普通数字"。

### 写 xlsx：反过来生成

生成更简单：按 `SpreadsheetML` 最小子集拼 XML，zip 回去。

```python
def write_xlsx(rows, path):
    def col_name(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    sheet = '<?xml version="1.0"?><worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (
        NS[1:-1],
        "".join('<row r="%d">%s</row>' % (ri + 1,
                "".join('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'
                        % (col_name(ci), ri + 1, esc(str(cv)))
                        for ci, cv in enumerate(r)))
                for ri, r in enumerate(rows)))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
```

用 `inlineStr` 而不是共享字符串——生成端省掉建表逻辑，Excel 照样正常打开。**实测写出的文件能被 Excel 和 WPS 直接打开。**

## 三个组件：一条完整的 Excel 流水线

三个组件各自独立、也能串成工作流：

| 组件 | 输入 | 输出 | 测试 |
|---|---|---|---|
| `excel_merge_kit` | 多个 xlsx/csv | 一张去重后的总表（带来源文件名） | 5/5 |
| `excel_pivot_kit` | 一张表 + 分组维度 | 聚合汇总表（sum/count/avg/max/min） | 6/6 |
| `uibot_excel_recon` | 两张表 + 主键列 | 差异报告（仅A有/仅B有/值不一致/一致） | 6/6 |

### 1. 合并：`excel_merge_kit`

多表合并的核心难点是**表头不一致**和**去重策略**。我的做法：

- 表头取并集，缺的列补空——不用要求各个表列完全一致；
- 每行加一列 `来源文件`，业务能追溯到这条数据从哪来；
- 按主键去重时保留**后出现的**（通常后给的表是更新的）。

```python
from merge_engine import read_any, merge

result = merge(["订单_华东.xlsx", "订单_华南.xlsx"], key="订单号", dedup=True)
# result['rows']     —— 合并后的行（字典列表）
# result['columns']  —— 表头并集
# result['sources']  —— {'订单_华东.xlsx': 2, '订单_华南.xlsx': 2} 每文件行数
# result['stats']    —— {'input_rows': 4, 'output_rows': 3, 'files': 2, 'dedup': True}
# 实测：堆叠 4 行 → 去重后 3 行 → 回读校验通过
```

### 2. 透视：`excel_pivot_kit`

替代手工透视表和 SUMIFS。声明式配置比拖拽字段更适合 RPA：

```python
from pivot_engine import read_any, pivot, write_xlsx

rows = read_any("orders.xlsx")
result = pivot(rows, group_by=("区域",), aggs=[
    {"col": "金额", "func": "sum",   "as": "金额合计"},
    {"col": "金额", "func": "count", "as": "笔数"},
    {"col": "金额", "func": "avg",   "as": "平均金额"},
])
# result['summary']      —— 汇总行（字典列表，含分组列与聚合列）
# result['group_cols']   —— ['区域']
# result['value_cols']   —— ['金额合计', '笔数', '平均金额']
# result['stats']        —— {'input_rows': 5, 'groups': 2}
# 实测输出：华东 450 / 3 笔 / 150 均，华南 420 / 2 笔 / 210 均
```

这里踩过一个真 bug，值得一说：初版 `_num()` 一律返回 `float`，
导致整数 450 被写成 `"450.0"`，业务看到汇总表里全是小数当场炸毛。
修复是**整数走 int、带小数的才走 float**——数值处理里"看起来不会出错"的地方最会出错。

### 3. 核对：`uibot_excel_recon`

最贴近真实业务的一个。按主键把两张表分成四类：

```python
from recon_engine import read_xlsx, read_csv, reconcile, write_report

result = reconcile(
    read_xlsx("系统.xlsx"),
    read_csv("台账.csv"),
    key="订单号",                 # 主键列
    compare_cols=None,           # None = 除主键外全部列都比对
)
# result['only_in_a']      —— 只在 A 表有的行（行字典）
# result['only_in_b']      —— 只在 B 表有的行
# result['value_mismatch'] —— 两边都有但某些列不同，实测结构：
#     [{"key": "a002", "a_row": 4, "b_row": 4,
#       "diffs": [{"col": "金额", "a": "200", "b": "250"}]}]
# （diffs 里每个元素是一处列差异，两张表差几列就有几项）
# result['matched']        —— 完全一致的行
# result['stats']          —— {total_a, total_b, only_a, only_b, mismatch, matched}
n = write_report(result, "核对报告.csv")   # 返回写出的行数
```

> 导入方式：把组件目录（如 `uibot_excel_recon/`）整个拷进你的 UiBot 工程根目录，
> 就能直接 `from recon_engine import ...`；三个组件各自独立，互不依赖。

比对前对数值做归一化（`"200"`、`"200.0"`、`"￥200"` 都判为一致），
避免把格式差异报成业务差异——**误报率高的核对工具，业务用一次就不会再用第二次。**

## 怎么在 UiBot 里用

UiBot Creator 支持在流程中调用 Python 代码块，所以接入就是三步：

1. 把组件目录拷到机器人工程下（或者整个工程放进 `project.cfg` 指定的目录）；
2. Python 代码块里 `import` 对应模块；
3. 用 UiBot 原生的 Excel 读取指令拿数据 → 传给组件的函数 → 把结果写回。

组件里我留了 `main.py` 作为入口示例，`python main.py` 直接能看到演示输出。

## 写在最后

这三个组件的共同点是：**解决的是业务每天都在做的重复劳动**。
RPA 工程师最值钱的能力不是会画流程，而是能看出"这件事值得被自动化"。

代码全部开源（MIT），Gitee 上可以直接 clone：
[excel_merge_kit](https://gitee.com/ZhiYIlang/excel_merge_kit) ·
[excel_pivot_kit](https://gitee.com/ZhiYIlang/excel_pivot_kit) ·
[uibot_excel_recon](https://gitee.com/ZhiYIlang/uibot_excel_recon)

---

**作者**：支一郎 · RPA 开发 / AI Agent 方向 · [作品集](https://zhiyilang.github.io)

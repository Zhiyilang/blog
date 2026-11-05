# 没有浏览器怎么测 RPA 流程？rpa2test 的 Mock 干跑与「宣称=实测」闸门

> 基于真实开源项目 [rpa2test](https://gitee.com/ZhiYIlang/rpa2test)（纯标准库，21 项单元测试全绿）。
> 文中每一条输出都是我在这台机器上跑出来的，命令可复现。

## 一、RPA 团队最贵的成本，不是开发

问一个做了两年以上 RPA 的人：改一个老流程，时间花在哪？

答案几乎一致：**三分之二花在"真机点一遍"上。**

- 想改登录流程的一个选择器，得连到测试环境真登一次；
- 想加一个余额断言，得等业务给一个有数据的账号；
- 最麻烦的是**回归**——改了第 3 步，谁也不知道第 17 步是不是被带崩了；
- 于是大家的选择是：**不改**。流程越捂越臭，最后整条重写。

根子在于：RPA 流程的逻辑和它依赖的浏览器**被焊死在一起**。
测试一个纯逻辑问题（选择器写错、变量名拼错、循环边界），却要付出启动整个系统的代价。

`rpa2test` 的思路很简单：**把流程逻辑从浏览器里抽出来，喂一份 mock 数据进去跑。**

## 二、dryrun：一份 JSON + 一份 mock

流程用影刀 / UiBot 风格的 JSON 描述：

```json
{
  "name": "BankLogin",
  "description": "登录并抽取余额，断言为正",
  "steps": [
    {"type": "navigate", "attrs": {"url": "https://bank.example.com/login"}},
    {"type": "input", "attrs": {"selector": "#user", "value": "zhiyilang"}},
    {"type": "input", "attrs": {"selector": "#pass", "value": "s3cr3t"}},
    {"type": "click", "attrs": {"selector": "#submit"}},
    {"type": "wait", "attrs": {"ms": 500}},
    {"type": "extract", "attrs": {"selector": "#balance", "save_as": "balance"}},
    {"type": "assert", "attrs": {"expr": "balance > 0"}}
  ]
}
```

mock 只描述"页面会返回什么"：

```json
{ "inputs": {}, "data": { "#balance": 4200 } }
```

跑起来：

```bash
python -m rpa2test dryrun examples/login_flow.json --mock examples/login_expect.json
```

实测输出：

```
# Dry-run: BankLogin
# Demo: login then extract balance, assert positive.
[navigate:https://bank.example.com/login] navigate -> https://bank.example.com/login
[input:#user] input #user = zhiyilang
[input:#pass] input #pass = s3cr3t
[click:#submit] click #submit
[wait:wait] wait 500ms
[extract:#balance] extract #balance -> 4200 => 4200
[assert:assert] assert balance > 0 -> True => True

context keys: ['balance']
inputs set: 2 | clicks: 1
DRY-RUN OK
```

七步流程的执行轨迹、最终 context、输入数、点击数，全部打印。
断言失败时退出码 `1`——这一条决定了它**能不能卡进 CI**：

```bash
$ python -m rpa2test verify examples/verified_login_flow_fail.json \
    --mock examples/login_expect_fail.json
DRY-RUN FAILED: assertion failed: balance > 0
$ echo $?
1
```

支持的步骤：`navigate / input / click / wait / extract / llm / loop / condition / assert`，
`loop` 支持 `{var}` 占位渲染，`condition` 走安全表达式求值。

## 三、真正想讲的：dryrun 不够，「沉默不等于证明」

上面那个 `DRY-RUN OK` 有个致命问题：**它只证明流程跑通了，没证明流程声称的效果发生了。**

一个典型的例子：流程文档里写着"运行后生成 report.csv 并写入汇总结果"。
`dryrun` 全程没碰文件系统，它当然会说 OK——**它根本不知道有这个声明**。

于是有了第二个子命令 `verify`。做法是：**流程必须自己声明证据**，工具读回真实产物复核。

```json
"expect": [
  {"kind": "context_equals", "key": "balance", "value": 4200},
  {"kind": "artifact_exists", "path": "report.csv"},
  {"kind": "artifact_contains", "path": "report.csv", "contains": "OK"},
  {"kind": "assert", "expr": "balance > 100"}
]
```

```bash
$ python -m rpa2test verify examples/verified_login_flow.json \
    --mock examples/login_expect.json
# Verify: BankLoginVerified
[PASS] context_equals: balance == 4200 (got 4200)
[PASS] assert: balance > 100
VERIFIED
```

关键的设计取舍在这一条：**如果流程没有声明任何证据，`verify` 直接退出码 1。**

```python
# verifier.py：没有声明证据 = 无法证实，直接失败
if not expectations:
    print("[SKIP] no expectations declared — cannot verify")
    print("VERIFICATION FAILED")
    return 1        # 沉默不等于证明
```

实测（拿一个没有 `expect` 块的流程去跑 `verify`）：

```
$ python -m rpa2test verify examples/login_flow.json --mock examples/login_expect.json
# Verify: BankLogin
[SKIP] no expectations declared — cannot verify
VERIFICATION FAILED
$ echo $?
1
```

我见过太多"绿色即成功"的自动化：CI 挂了绿勾，评审点了头，上线三天才发现报表是空的。
问题不在于谁偷懒，而在于**没有任何机制要求流程说出"我该产生什么"**。
把"声明证据"变成硬门槛，撒谎的成本就高于说实话的成本。

这一条也是我自己写代码时守的规矩：**宣称=实测**。工具不过是把这条规矩变成了可执行的东西。

## 四、一个容易被忽略的点：表达式沙箱

`assert` 和 `condition` 要执行用户写的表达式，而流程 JSON 经常来自不可信的第三方
（下载的模板、同事发的、网上抄的）。直接 `eval()` 等于把机器交出去。

`rpa2test` 的做法是**白名单 AST 节点**：只放行比较、逻辑运算、下标、`len()` 这类节点，
属性访问、函数调用（除白名单内建）、`__import__` 一律拒绝。

实测：

```python
>>> from rpa2test.runtime import _safe_eval
>>> _safe_eval('1 + 1', {})
2
>>> _safe_eval('len("abc") > 2', {})
True
>>> _safe_eval('__import__("os").system("echo pwned")', {})
ValueError: forbidden call
```

第三条是重点：**一个能跑在 CI 里、读取外部流程文件的工具，表达式求值必须是沙箱。**
这一条做不到，"零依赖干跑"就是个后门。

## 五、落地：怎么塞进现有 CI

仓库里已经带了一份 `.github/workflows/tests.yml`（GitHub Actions；推到 Gitee 可用 Gitee Go），
三版本矩阵 + 一个敌意 locale job，原文如下：

```yaml
name: tests

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.8", "3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m unittest discover -s tests

  hostile-locale:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: run under non-English locale (asserts no locale dependency)
        env:
          LC_ALL: C
          LANG: C
        run: python -m unittest discover -s tests
```

想把它变成真正的流程回归门，加一个遍历 `flows/` 的 job 即可
（这段是按需扩展，不是仓库现有内容）：

```yaml
  flow-regression:
    steps:
      - run: |
          for f in flows/*.json; do
            python -m rpa2test verify "$f" --mock mocks/$(basename "$f" .json).json
          done
```

`hostile-locale` 那一 job 是踩过的坑：早版本有处字符串处理依赖英文环境，切到 C locale 就挂。
**不依赖语言环境的代码，和零依赖一样，是交付给别人的基本礼貌。**

21 项测试覆盖解析、运行时、核验器三层，纯标准库零依赖，
clone 下来 `python -m unittest discover -s tests` 即可跑（Python ≥ 3.8）。

## 六、小结

RPA 的流程逻辑本质上就是普通程序逻辑：有条件、有循环、有变量、有断言。
它之所以难测，只是因为**被绑在了浏览器上**。拆开之后，你能拿到全部现成的工程手段：
mock、回归、CI 卡点、沙箱求值。

而比"能测"更重要的一条是：**要求流程自己声明该产生什么，然后读回产物复核。**
工具名里的 `test` 是这个意思，`verify` 也是这个意思。

---

**项目地址**：[gitee.com/ZhiYIlang/rpa2test](https://gitee.com/ZhiYIlang/rpa2test)（MIT，21 项测试全绿）
同系列：[rpa2agent](https://gitee.com/ZhiYIlang/rpa2agent)（流程→Agent 编译器）·
[rpa2mcp](https://gitee.com/ZhiYIlang/rpa2mcp)（流程→MCP Server）·
[rpaaudit](https://gitee.com/ZhiYIlang/rpaaudit)（流程静态审计）

**作者**：支一郎 · RPA 开发 / AI Agent 方向 · [作品集](https://zhiyilang.github.io)

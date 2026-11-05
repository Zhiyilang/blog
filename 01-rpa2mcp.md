# 把 RPA 流程一键编译成 MCP Server：rpa2mcp 设计与实战

> 本文基于真实开源项目 [rpa2mcp](https://gitee.com/ZhiYIlang/rpa2mcp)（纯标准库，4 项单元测试全绿）写成。
> 文中所有代码与数字均为仓库实测结果：7 步示例流程编译产物 3219 字节、9 个 MCP 工具。

## 一、问题：你的 RPA 脚本，Agent 调不动

2026 年的现实是：一边是 MCP（Model Context Protocol）成了 Agent 调用外部能力的事实标准，
另一边是无数 RPA 脚本躺在影刀、UiBot、Selenium 工程里，跑得好好的，但 **LLM 完全看不见它们**。

常见的两条路都有问题：

1. **用 Agent 框架重写一遍流程** —— 成本高、风险大，一个 7 步的下单流程重写两天，还不敢上线；
2. **给 RPA 引擎套个 HTTP 接口** —— 你得到的是一个「黑盒按钮」，Agent 只知道"能调用"，
   不知道每一步在干什么、参数是什么、顺序是什么。

我想要的是第三条路：**不重写逻辑，只补一个适配层，把流程的每一步暴露成 MCP 工具**。

这就是 `rpa2mcp` 做的事。

## 二、设计思路：JSON 流程 → 类型化工具

MCP 工具的核心是「有名字、有 docstring、有类型标注的函数」。所以只要能把 RPA 流程翻译成
一组带类型的函数，问题就解决了。

### 2.1 输入：一份中立的流程 JSON

先定义一个与具体引擎无关的流程描述格式（贴近影刀 / UiBot 的指令习惯）：

```json
{
  "name": "下单并查询物流",
  "description": "登录后下单，并逐单查询物流状态",
  "steps": [
    {"type": "navigate", "attrs": {"url": "https://shop.example.com/login", "description": "打开登录页"}},
    {"type": "input",   "attrs": {"selector": "#user", "value": "{{user}}"}},
    {"type": "input",   "attrs": {"selector": "#pass", "value": "{{password}}"}},
    {"type": "click",   "attrs": {"selector": "#submit"}},
    {"type": "extract", "attrs": {"selector": ".order-no", "store": "order_no", "description": "抓取订单号"}},
    {"type": "loop",    "attrs": {"items": "orders", "var": "o", "description": "逐单查询物流"},
     "body": [
       {"type": "click",   "attrs": {"selector": ".track", "value": "{{o.id}}"}},
       {"type": "extract", {"attrs": {"selector": ".status", "store": "o.status"}}
     ]},
    {"type": "llm", "attrs": {"prompt": "总结物流状态并标注异常", "store": "summary"}}
  ]
}
```

几个关键设计：

- **`type` 是稳定的小集合** —— `navigate / input / click / extract / loop / llm / ...`，
  新增一种步骤只需在生成器里注册一条参数规则；
- **`attrs.description` 是人话注释** —— 原样搬进生成代码的 docstring，Agent 靠它理解工具用途
  （**这是最值得养成的习惯：给每一步写 description，Agent 才看得懂你的流程**）；
- **`store` 是变量绑定** —— 这一步的结果存进哪个变量，供后续步骤引用；
- **`body` 支持嵌套** —— `loop` 里的子步骤会被**提升为独立的顶层工具**（下面细说）。

### 2.2 参数签名从哪来：按步骤类型推导

这是最需要说清楚的一点。函数签名**不是**靠扫描 `{{user}}` 这类模板变量得来的，而是**按步骤类型静态推导**：

```python
def _param_sig(step):
    params = []
    if step.type == "navigate": params.append("url: str")
    if step.type in ("click", "input"): params.append("selector: str")
    if step.type in ("input",):          params.append("value: str = ''")
    if step.type == "llm":               params.append("prompt: str")
    if step.type == "extract":           params.append("store: str = ''")
    if step.type == "loop":              params.append("items: str = ''"); params.append("var: str = ''")
    ...
```

这样做的好处是**签名稳定可预测**：Agent 拿到工具列表时，参数结构跟流程写法无关，
不会因为某一步多写了一个 `{{变量}}` 就多出一个参数、导致 Agent 调用时困惑。

代价也要讲明白：**模板变量目前是原样透传的**。上例中 `"value": "{{user}}"` 会作为字面值
传给 `driver.input(...)`，由你的 `Driver` 实现去决定怎么解析（替换成真实用户名、还是从环境变量读）。
把模板解析做成生成期特性是明确的 roadmap 项——但那需要先定义一套变量作用域规则，
在没想清楚之前，我选择透传而不是瞎猜。

### 2.3 编译：两步走，不搞宏魔术

```python
from rpa2mcp import parse_flow_json
from rpa2mcp.generator import generate_mcp_server

flow = parse_flow_json(open("examples/order_flow.json", encoding="utf-8").read())
code = generate_mcp_server(flow)          # 返回 str，直接可写文件
```

`parse_flow_json` 负责解析与校验（未知步骤类型、结构不合法都在**编译期**报错，
而不是等运行时 Agent 调用了才炸），`generate_mcp_server` 负责代码生成。

**编译期报错**值得强调：流程写错是 RPA 最高频的事故源，把它前移到加载阶段，
是这类工具能省下的最大一笔隐性成本。

### 2.4 生成：每个步骤一个 MCP 工具

实测生成的 `server.py`（3219 字节）关键片段：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("rpa2mcp: 下单并查询物流")

class Driver:
    """Replace each stub with your RPA engine call."""
    def navigate(self, url: str):
        raise NotImplementedError("implement navigate() with your browser engine")
    def input(self, selector: str, value: str = ""):
        raise NotImplementedError("implement input()")
    def click(self, selector: str):
        raise NotImplementedError("implement click()")
    # ...

driver = Driver()

@mcp.tool()
def step_1_navigate(url: str) -> str:
    """打开登录页"""
    return str(driver.navigate(url=url))

@mcp.tool()
def step_2_input(selector: str, value: str = '') -> str:
    """input action"""
    return str(driver.input(selector=selector, value=value))

@mcp.tool()
def step_5_extract(selector: str, store: str = '') -> str:
    """抓取订单号"""
    return str(driver.extract(selector=selector, store=store))

if __name__ == "__main__":
    # Transports: stdio by default; add --transport sse for remote agents.
    mcp.run()
```

四个从实测里读出来的细节：

1. **7 步流程 → 9 个工具**：`loop` 体内的两个子步骤被提升为独立的顶层工具
   （`step_7_click` / `step_8_extract`）。这不是 bug——MCP 没有"子工具"概念，
   把循环体摊平成可单独调用的工具，Agent 才能灵活地"查这一单"而不是"跑整个循环"；
2. **docstring 有回退**：`s.get("description") or f"{s.type} action"`。写了 description 的步骤
   （`step_1_navigate` → "打开登录页"）Agent 看得懂，没写的就只剩 "input action" 这种空话——
   **工具的描述质量，直接决定 Agent 会不会用错它**；
3. **Driver 是唯一的手写部分**：一个类、每个步骤类型一个方法，把 MCP 世界接到你现有引擎上；
4. **默认 stdio 传输**，加 `--transport sse` 就能给远程 Agent 用。

### 2.5 关键取舍：为什么不做「运行时解释器」

另一条路是写一个运行时，加载 JSON 后直接解释执行。我选了**代码生成**：

| | 代码生成 | 运行时解释 |
|---|---|---|
| 出错时机 | 编译期（流程加载即报错） | 运行期（Agent 调到才炸） |
| 可读性 | 生成的是普通 .py，能打断点、能改 | 黑盒 |
| 分发 | 生成文件可直接交给同事 | 必须连带运行时 |
| 与 MCP 集成 | 直接就是 `@mcp.tool()` | 要额外包一层 |

代价是生成的代码有重复——7 步流程无所谓，500 步流程才会考虑折中。
RPA 流程普遍在几十步量级，代码生成是更优解。

## 三、实测：跑一遍看看

```bash
git clone https://gitee.com/ZhiYIlang/rpa2mcp.git
cd rpa2mcp
python -m unittest discover -s tests -v     # 4 项测试
python -m rpa2mcp generate examples/order_flow.json -o server.py
```

仓库里的 4 项测试，覆盖的是这个方案真正的风险点：

- `test_parse` —— 示例流程能被完整解析，`loop` 的 `body` 嵌套不丢；
- `test_generated_is_valid_python_without_mcp_installed` —— **没装 `mcp` 包的机器上也能编译**，
  产物至少是语法合法的 Python（本机当时就处于这个状态，这条测试是硬需求）；
- `test_generated_has_mcp_tool_decorators` —— 产物里 `@mcp.tool()` 数量与步骤数匹配；
- `test_cli_end_to_end_writes_runnable_file` —— 命令行端到端，产物含 `class Driver`。

其中第二条最实在：**编译链路不许依赖 `mcp` 包**，否则没装 MCP 环境的 RPA 机器连代码都生成不了。

## 四、一个真实的使用场景

把上面那个流程接到一个已有的 UiBot 工程上，实际改动只有两处。

**第一处**，写 `Driver`，内部调用 UiBot 的指令 API——你原来的逻辑一行没改：

```python
class Driver:
    def __init__(self, page):
        self.page = page
    def click(self, selector: str):
        return self.page.click(selector)
    def input(self, selector: str, value: str = ""):
        # 模板变量在这里解析：把 {{user}} 换成真实值
        return self.page.input(selector, self.resolve(value))
```

**第二处**，在 Claude Desktop 或任意 MCP Client 的配置里指向生成的 `server.py`。

然后你就可以对 Agent 说：

> "帮我把这批 12 个订单的物流查一下，异常的标出来"

Agent 自己决定：先调 `step_1_navigate`，再 `step_2_input` / `step_3_input`，
逐个 `step_7_click` 查询、`step_8_extract` 抓状态，最后 `step_9_llm` 总结。
**你的 RPA 代码一行没重写，但它现在长在 Agent 身上了。**

## 五、工具箱全景：四个工具各管一段

`rpa2mcp` 是「RPA → AI Agent」工具箱的一环，另外三个姊妹工具解决邻近问题：

| 工具 | 解决的问题 | 测试 |
|---|---|---|
| [rpa2agent](https://gitee.com/ZhiYIlang/rpa2agent) | 流程 → 可运行 Agent 计划 + 生成独立 .py | 26 项 |
| [rpa2test](https://gitee.com/ZhiYIlang/rpa2test) | 无浏览器 Mock 干跑，流程逻辑先测再上线 | 21 项 |
| [rpaaudit](https://gitee.com/ZhiYIlang/rpaaudit) | 静态审计：硬编码密钥、死循环、脆弱选择器 | 10 项 |
| **rpa2mcp** | 流程 → MCP Server，让 Agent 调用 | 4 项 |

合计 **61 项测试全绿，纯标准库零依赖**——这是刻意的：RPA 工程师的机器上往往装着一堆版本混乱的库，
零依赖意味着 clone 下来就一定能跑。

## 六、结语

Agent 时代真正稀缺的不是"会不会写 Agent"，而是**把已有生产力接进 Agent 的能力**。
对 RPA 工程师来说，你手里那些跑了几年的流程就是资产——缺的只是那一层编译器和适配层。

流程还是那份流程，只是现在，它会回答大模型的话了。

---

**项目地址**：[gitee.com/ZhiYIlang/rpa2mcp](https://gitee.com/ZhiYIlang/rpa2mcp)（MIT，欢迎 Issue / PR）
**作者**：支一郎 · RPA 开发 / AI Agent 方向 · [作品集](https://zhiyilang.github.io)

"""A failure output over its budget has its runs of frames outside the project collapsed first (plan SZ.3).

The fix's failure text was cut from the front at 6,000 characters and a
command's output to its head and tail. A traceback through a framework, a test
runner and the runtime spends that budget on frames nobody in the project can
change, and on a large product the cut then fell on the project's own frames
and the assertion between them. Which frames are outside is read from the
path each names, in every runtime's shape; an output within its budget is
handed over exactly as it was.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.analysis.tracebacks import without_outside_frames


@pytest.fixture
def workspace(tmp_path):
    for path in ("svc/routes.py", "src/handler.js", "internal/api/orders.go", "src/main/java/acme/OrderService.java",
                 "app/models/order.rb", "app/Http/OrderController.php", "Api/Orders.cs"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("\n")
    return tmp_path


def _assert_collapsed(before: str, workspace, kept: list[str], gone: list[str], omitted: int) -> str:
    after = without_outside_frames(before, workspace)
    for line in kept:
        assert line in after, line
    for line in gone:
        assert line not in after, line
    assert f"[{omitted} frames outside the project omitted]" in after
    return after


def test_python(workspace):
    before = """Traceback (most recent call last):
  File "/workspace/svc/routes.py", line 40, in create
    return store.save(item)
  File "/usr/lib/python3.12/site-packages/sqlalchemy/orm/session.py", line 2200, in save
    self._flush()
  File "/usr/lib/python3.12/site-packages/sqlalchemy/orm/session.py", line 4100, in _flush
    flush_context.execute()
  File "/usr/lib/python3.12/site-packages/sqlalchemy/orm/unitofwork.py", line 460, in execute
    rec.execute(self)
  File "/usr/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1960, in _exec
    cursor.execute(statement, parameters)
sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: items.name"""
    after = _assert_collapsed(
        before, workspace,
        kept=['File "/workspace/svc/routes.py", line 40, in create', "return store.save(item)",
              'File "/usr/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1960, in _exec',
              "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed"],
        gone=["self._flush()", "unitofwork.py"], omitted=3,
    )
    assert after.count("\n") < before.count("\n")


def test_pytest_s_short_traceback(workspace):
    before = """svc/routes.py:40: in create
    return store.save(item)
/usr/lib/python3/site-packages/_pytest/runner.py:341: in from_call
    result = func()
/usr/lib/python3/site-packages/_pytest/runner.py:262: in <lambda>
    lambda: ihook(item=item, **kwds)
/usr/lib/python3/site-packages/pluggy/_hooks.py:513: in __call__
    return self._hookexec(self.name, self._hookimpls)
/usr/lib/python3/site-packages/pluggy/_manager.py:120: in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs)
E   AssertionError: 200 != 404"""
    _assert_collapsed(before, workspace, kept=["svc/routes.py:40: in create", "E   AssertionError: 200 != 404",
                                               "pluggy/_manager.py:120: in _hookexec"],
                      gone=["result = func()"], omitted=3)


def test_node(workspace):
    before = """TypeError: Cannot read properties of undefined (reading 'id')
    at handler (/workspace/src/handler.js:12:20)
    at Layer.handle [as handle_request] (/workspace/node_modules/express/lib/router/layer.js:95:5)
    at next (/workspace/node_modules/express/lib/router/route.js:149:13)
    at Route.dispatch (/workspace/node_modules/express/lib/router/route.js:119:3)
    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)"""
    _assert_collapsed(before, workspace, kept=["at handler (/workspace/src/handler.js:12:20)", "TypeError: Cannot read"],
                      gone=["layer.js:95:5"], omitted=3)


def test_go(workspace):
    before = """panic: runtime error: invalid memory address or nil pointer dereference
goroutine 7 [running]:
acme/internal/api.(*Orders).Create(0xc000010000, {0x0, 0x0})
\t/workspace/internal/api/orders.go:31 +0x1d
net/http.HandlerFunc.ServeHTTP(0xc0000a4000, {0x6f8e20, 0xc0000e2000}, 0xc0000c8000)
\t/usr/local/go/src/net/http/server.go:2136 +0x29
github.com/gin-gonic/gin.(*Context).Next(...)
\t/root/go/pkg/mod/github.com/gin-gonic/gin@v1.9.1/context.go:174
github.com/gin-gonic/gin.(*Engine).handleHTTPRequest(0xc0000d6000, 0xc0000e4000)
\t/root/go/pkg/mod/github.com/gin-gonic/gin@v1.9.1/gin.go:620 +0x65a
net/http.serverHandler.ServeHTTP({0xc0000a2000}, {0x6f8e20, 0xc0000e2000}, 0xc0000c8000)
\t/usr/local/go/src/net/http/server.go:2938 +0x8e"""
    _assert_collapsed(before, workspace, kept=["/workspace/internal/api/orders.go:31", "panic: runtime error",
                                               "/usr/local/go/src/net/http/server.go:2938"],
                      gone=["context.go:174"], omitted=3)


def test_java(workspace):
    before = """java.lang.IllegalStateException: order 7 not found
\tat acme.OrderService.find(OrderService.java:44)
\tat org.springframework.aop.framework.ReflectiveMethodInvocation.proceed(ReflectiveMethodInvocation.java:186)
\tat org.springframework.aop.framework.CglibAopProxy.intercept(CglibAopProxy.java:704)
\tat java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:103)
\tat java.base/java.lang.reflect.Method.invoke(Native Method)
\t... 23 more"""
    _assert_collapsed(before, workspace, kept=["at acme.OrderService.find(OrderService.java:44)",
                                               "IllegalStateException: order 7 not found"],
                      gone=["CglibAopProxy.java:704"], omitted=4)


def test_ruby(workspace):
    before = """NoMethodError: undefined method `total' for nil
/workspace/app/models/order.rb:12:in `price'
/usr/local/bundle/gems/activesupport-7.1.0/lib/active_support/callbacks.rb:110:in `run_callbacks'
/usr/local/bundle/gems/actionpack-7.1.0/lib/abstract_controller/base.rb:224:in `process_action'
/usr/local/bundle/gems/rack-3.0.8/lib/rack/sendfile.rb:114:in `call'
/usr/local/bundle/gems/puma-6.4.0/lib/puma/server.rb:1099:in `handle_request'"""
    _assert_collapsed(before, workspace, kept=["/workspace/app/models/order.rb:12:in `price'", "NoMethodError"],
                      gone=["callbacks.rb:110"], omitted=3)


def test_php(workspace):
    before = """PHP Fatal error:  Uncaught TypeError: total(): Argument #1 must be of type int
#0 /var/www/app/Http/OrderController.php(31): total()
#1 /var/www/vendor/laravel/framework/src/Illuminate/Routing/Controller.php(54): show()
#2 /var/www/vendor/laravel/framework/src/Illuminate/Routing/ControllerDispatcher.php(43): callAction()
#3 /var/www/vendor/laravel/framework/src/Illuminate/Routing/Route.php(260): dispatch()
#4 /var/www/vendor/laravel/framework/src/Illuminate/Routing/Route.php(205): runController()
#5 {main}"""
    _assert_collapsed(before, workspace, kept=["#0 /var/www/app/Http/OrderController.php(31): total()", "#5 {main}"],
                      gone=["Controller.php(54)"], omitted=4)


def test_dotnet(workspace):
    before = """System.InvalidOperationException: Sequence contains no elements
   at System.Linq.ThrowHelper.ThrowNoElementsException()
   at Api.Orders.Get(Int32 id) in /src/Api/Orders.cs:line 27
   at Microsoft.AspNetCore.Mvc.Infrastructure.ActionMethodExecutor.Execute(ActionContext context)
   at Microsoft.AspNetCore.Mvc.Infrastructure.ControllerActionInvoker.InvokeActionMethodAsync()
   at Microsoft.AspNetCore.Mvc.Infrastructure.ControllerActionInvoker.Next(State& next)
   at Microsoft.AspNetCore.Routing.EndpointMiddleware.Invoke(HttpContext httpContext)"""
    _assert_collapsed(before, workspace, kept=["at Api.Orders.Get(Int32 id) in /src/Api/Orders.cs:line 27",
                                               "System.InvalidOperationException"],
                      gone=["ActionMethodExecutor.Execute"], omitted=3)


def test_two_frames_outside_are_left_as_they_are(workspace):
    before = """Traceback (most recent call last):
  File "/workspace/svc/routes.py", line 40, in create
    return store.save(item)
  File "/usr/lib/python3.12/site-packages/x/a.py", line 1, in save
    one()
  File "/usr/lib/python3.12/site-packages/x/b.py", line 2, in one
    two()
ValueError: no"""
    assert without_outside_frames(before, workspace) == before


def test_a_fix_s_failure_within_its_budget_is_as_it_was(tmp_path):
    from app.graph import rewritten_fixes

    printed = 'Traceback:\n' + "".join(f'  File "/usr/lib/python3/site-packages/x/m{n}.py", line 1, in f\n    g()\n' for n in range(5))
    defect = SimpleNamespace(actual_behavior=printed, reproduction_steps=[], description="")

    assert rewritten_fixes.what_failed(defect, tmp_path) == printed.strip()


def test_a_fix_s_long_failure_keeps_the_assertion_the_frames_pushed_out(workspace):
    from app.graph import rewritten_fixes

    frames = "".join(
        f'  File "/usr/lib/python3.12/site-packages/framework/layer{n}.py", line {n}, in call\n    return inner(request)\n'
        for n in range(120)
    )
    printed = (
        "Traceback (most recent call last):\n" + frames
        + '  File "/workspace/svc/routes.py", line 40, in create\n    return store.save(item)\n'
        + "AssertionError: expected 404, got 200"
    )
    defect = SimpleNamespace(actual_behavior=printed, reproduction_steps=[], description="")
    assert len(printed) > rewritten_fixes.MOST_FAILURE_CHARACTERS

    shown = rewritten_fixes.what_failed(defect, workspace)

    assert "AssertionError: expected 404, got 200" in shown
    assert 'File "/workspace/svc/routes.py", line 40, in create' in shown
    assert "[120 frames outside the project omitted]" in shown


def test_what_the_model_is_told_uses_none_of_the_banned_words(workspace, monkeypatch, tmp_path):
    import re

    from app.tools import sandbox

    banned = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
    monkeypatch.setattr(sandbox, "MAX_OUTPUT_SIZE", 400)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    frames = "".join(f"    at fn (/w/node_modules/x/l{n}.js:1:1)\n" for n in range(30))
    shown = sandbox._truncate("Error: no\n" + frames + "done\n", "unit", str(workspace))
    assert "frames outside the project omitted" in shown and "full output saved as" in shown
    assert not banned.search(shown.replace("/w/", "")), shown


def test_a_command_s_output_within_its_cap_is_as_it_was():
    from app.tools import sandbox

    text = "x" * 10 + "\n  at next (/w/node_modules/a.js:1:1)\n" * 3
    assert sandbox._truncate(text) == text


def test_a_command_s_long_output_keeps_the_project_s_frames_in_the_middle(workspace, monkeypatch, tmp_path):
    from app.tools import sandbox

    monkeypatch.setattr(sandbox, "MAX_OUTPUT_SIZE", 4_000)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    noise = "".join(f"    at fn{n} (/workspace/node_modules/framework/lib/layer{n}.js:{n}:5)\n" for n in range(200))
    text = (
        "PASS src/a.test.js\n" * 40 + "TypeError: Cannot read properties of undefined\n" + noise
        + "    at handler (/workspace/src/handler.js:12:20)\n" + noise + "Tests: 1 failed, 40 passed\n"
    )
    assert len(text) > 4_000

    shown = sandbox._truncate(text, "unit", str(workspace))

    assert "at handler (/workspace/src/handler.js:12:20)" in shown
    assert "TypeError: Cannot read properties of undefined" in shown
    assert "frames outside the project omitted" in shown
    assert len(shown) < len(text)

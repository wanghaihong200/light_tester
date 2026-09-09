"""Schema 契约测试:PATCH 模型的部分更新语义。

部分 PATCH 语义依赖「省略字段 = 不修改」,这要求 PATCH 模型每个字段默认值都是 None。
两个 PATCH 模型都继承自对应 Save 模型,一旦新增字段漏覆写,会继承 Save 的非 None 默认值,
router 的 `if payload.x is not None` 恒真 → 部分 PATCH 静默重置该字段
(真实案例:MockRulePatch 曾漏覆写 enable_template=False,规则列表启停开关只发 {"enabled"}
就会把模板渲染开关静默关掉)。本契约遍历全字段守住这条线。
"""
from app.schemas import MockInstancePatch, MockRulePatch

# 无白名单:当前两个 PATCH 模型的所有字段都没有「非 None 默认」的业务理由。
PATCH_MODELS = (MockInstancePatch, MockRulePatch)


def test_patch_models_every_field_defaults_to_none():
    for model in PATCH_MODELS:
        for name, field in model.model_fields.items():
            assert field.default is None, (
                f"{model.__name__}.{name} 默认值是 {field.default!r}:PATCH 模型字段必须默认 None"
                f"(部分 PATCH 语义),若是继承自 Save 模型请显式覆写为 None")
            assert field.default_factory is None, (
                f"{model.__name__}.{name} 设置了 default_factory:PATCH 模型字段必须默认 None")


def test_patch_models_every_field_optional():
    # 默认 None 之外,注解也必须是可空(避免「默认 None 但类型非 Optional」被 Pydantic 拒绝)
    for model in PATCH_MODELS:
        for name, field in model.model_fields.items():
            assert not field.is_required(), (
                f"{model.__name__}.{name} 是必填字段:PATCH 模型所有字段都应可省略")

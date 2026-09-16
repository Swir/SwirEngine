# SwirEngine 1.4 Editor Public API

The 1.4 editor-authoring milestone exposes one explicit opt-in facade:

```python
from swirengine.editor14 import (
    EditorAuthoringPlayController,
    EditorAuthoringSession,
    EditorAuthoringWorkspace,
    EditorSpecializedInspectors,
)
```

`swirengine.editor14` is the supported creator-facing import surface for the additive 1.4 editor
work. It collects the multi-selection authoring session, portable authoring state, authoring-aware
workspace/frontend, Play/Edit isolation controller, specialized material/physics/navigation
inspectors, asset-browser drag payloads, and the stable runtime preview types they compose with.

The facade intentionally does not change the package version or replace existing root imports while
1.4 is still an active milestone. Stable 1.x code can continue importing the existing editor APIs
exactly as before. New editor tooling can depend on one small module instead of importing private
helpers or relying on the source-file layout of the milestone implementation.

## Compatibility rule

Symbols listed by `swirengine.editor14.__all__` form the supported 1.4 authoring surface. Private
methods used internally to implement grouped transactions are not exported. Compatibility tests
verify that every declared symbol remains importable and that the core authoring, runtime isolation,
and specialized-inspector layers can be composed through the facade.

No `1.4.0` package version, release tag, or default-root API migration should be published until the
full 1.4 roadmap reaches its real completion gate.

# Final Lab visual QA

Source report SHA-256 verified before export:
`d6215d2e2a4999d8204923f507e1d85e8c22065774286ac771f0a6f6149022fa`.

Exported from the isolated current builder against its actual `.reflex` workspace. All displayed values derive from the executed fixture evaluation. No source changes were made during this inspection.

- `lab-desktop.png`: initial native desktop viewport, 1470 by 745 pixels. Actual selective mean 4119.3 ms, 100% fallback, and deployment withheld are visible.
- `lab-comparison.png`: actual six-policy timing comparison, held-out outcomes and failed promotion reasons.
- `lab-mobile.png`: actual final overview at 390 by 844 CSS pixels.

Final narrow layout passed: document scroll width equals viewport width at 390 pixels. The previous deployment-history overflow is fixed. The page stayed at 390 pixels after expanding a filtered record.

Interaction check: search `item-701001` plus `test` split returns exactly one real test record. Expanding it shows the units.py input and measured outcomes (focused incorrect, full correct). Sidebar section navigation works. Viewport override reset and agent-created inspection tab closed after QA.

Final HTML SHA-256:
`546905047e5927d46a198098d644e83e721fe91b6e32771052f9adb4887d705f`.

Temporary loopback preview server stopped after inspection. Earlier render artifacts are preserved outside final-v2 and should not be treated as final measurement evidence.

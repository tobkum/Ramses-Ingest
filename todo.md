# TODO: Ramses Naming Architect

This document serves as the master plan for implementing the **Ramses Naming Architect**, a visual rule-building engine designed to replace raw regex editing with a high-fidelity, tactile GUI.

---

## 1. Core Architecture: The Token System
Implement a system where naming rules are represented as a sequence of discrete, interactive objects (Tokens) rather than a single text string.

- [ ] **Dynamic Data Tokens**:
    - `[Sequence]`: Maps to `(?P<sequence>...)`
    - `[Shot]`: Maps to `(?P<shot>...)`
    - `[Step]`: Maps to `(?P<step>...)`
    - `[Version]`: Maps to `(?P<version>...)`
    - `[Project]`: Maps to `(?P<project>...)`
- [ ] **Structural Tokens**:
    - `[Separator]`: Specialized tokens for `_`, `-`, and `.`
    - `[Wildcard]`: Matches any generic text or digits.
    - `[Ignore]`: Explicitly marks parts of the filename to be discarded.
- [ ] **The "Shadow Rule" Logic**:
    - Detect "Greedy Collisions" (e.g., two dynamic tokens touching without a separator).
    - Implement a visual "Red Ghost" warning between tokens that lack a clear delimiter.

## 2. The Interactive Blueprint (Header UI)
The assembly area where rules are constructed.

- [ ] **Magnetic Assembly Bar**: A horizontal container where tokens can be dropped.
- [ ] **Drag-and-Drop Reordering**: Allow users to slide tokens left/right to change the parsing order.
- [ ] **The Constraint Inspector**:
    - Click-to-edit side panel for the active token.
    - **Padding**: Force digit width (e.g., "Must be 4 digits").
    - **Case Policy**: Force Uppercase, Lowercase, or TitleCase.
    - **Pattern Anchors**: "Start of Filename" (`^`) or "End of Filename" (`$`).
    - **Custom Regex Sub-patterns**: For advanced users to refine a specific token's match.

## 3. The Live Simulation Lab (Main Content)
A real-time feedback loop to verify rules against actual production data.

- [ ] **The Sandbox (Left Pane)**:
    - A drag-and-drop zone where users can paste or drop real filenames from a delivery.
    - Support for 10+ samples simultaneously.
- [ ] **The X-Ray Result (Right Pane)**:
    - Display the filenames with **Color-Coded Highlights** based on the current rule.
    - Cyan highlight for `[Shot]`.
    - Emerald highlight for `[Sequence]`.
    - Amber highlight for `[Version]`.
- [ ] **Success Heartbeat**:
    - Row glows green when a file is 100% successfully parsed.
    - Row shows "Muted Gray" or a red error icon on failure.
    - **Failure Diagnostics**: Tooltips explaining exactly where the parse broke (e.g., "Expected underscore at index 12, found 'A'").

## 4. Intelligent Automation: The "Auto-Healer"
Machine-assisted rule creation.

- [ ] **Pattern Recognition Engine**:
    - Analyze the common strings and incrementing numbers across the dragged samples.
- [ ] **Magic Wand Button**:
    - Automatically generate the top 3 most likely Token Blueprints based on the sample set.
    - One-click application of suggested rules.

## 5. The Naming Library & Studio Standards
Centralized management of naming conventions.

- [ ] **Vendor Presets**:
    - Built-in library for common formats (Technicolor, Framestore, CMX 3600, etc.).
- [ ] **Studio Repository**:
    - Ability to "Save to Studio" (persists to `config/default_rules.yaml`).
    - Syncing logic to ensure all workstations receive the updated rules instantly.

## 6. Developer Transparency (The X-Ray View)
Building trust with technical staff and pipeline TDs.

- [ ] **Regex Code Block**:
    - A collapsible footer showing the live-generated Python Regex.
    - Ensure it uses the `(?P<name>...)` group syntax required by the matcher.
- [ ] **Read-Only Code Mode**: Prevent accidental syntax errors while allowing power users to copy/paste the logic for documentation.

## 7. Aesthetic & UX Polish
- [ ] **Dark Mode Styling**: Deep charcoal and slate gray theme matching Ramses-Fusion.
- [ ] **Non-Blocking Slide-over**: The Architect should appear as a panel on the right, allowing the user to see the main Ingest List simultaneously.
- [ ] **Micro-animations**: Smooth transitions when tokens are added, removed, or reordered.

---
*Blueprint Version: 1.0.0*
*Last Refined: February 2026*

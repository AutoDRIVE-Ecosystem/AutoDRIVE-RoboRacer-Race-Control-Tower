# Decision Analysis Packs

Each selected penalty-rule option can provide an optional decision pack.

The frontend maps the option id to a slug by replacing underscores with hyphens:

- `rear_end_collision` loads `decision/rear-end-collision.html`, `.js`, and `.css`
- `unsafe_lateral_movement` loads `decision/unsafe-lateral-movement.html`, `.js`, and `.css`

If the `.html` file is missing, the option keeps the default `Opinion: To be added` text.

The JavaScript file must register a module:

```js
window.RctDecisionModules = window.RctDecisionModules || {};
window.RctDecisionModules["unsafe-lateral-movement"] = {
  mount(root, context) {
    return function render(frames) {
      context.setOpinion("Opinion: ...");
    };
  },
};
```

`context` includes:

- `initialFrames`
- `setOpinion(text)`
- `formatNumber(value, fractionDigits)`
- `displayRoboracerLabel(vehicleId)`

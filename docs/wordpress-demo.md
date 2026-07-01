# WordPress Demo

The WordPress plugin provides a browser-based demo for the Catalyst Grit page.

## Shortcode

```text
[catalyst_grit_demo]
```

## Data handling

The demo is client-side. It does not submit visitor inputs to Sustainable Catalyst by default.

## Suggested placement

Place it near the top of the Catalyst Grit page in a section titled `Live Demo`.

## Page CSS wrapper

```css
.scgrit-demo-shell {
  margin-top: 24px;
  padding: 0;
  background: #ffffff;
  border: 1px solid #d9d2c4;
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.045);
  overflow: hidden;
}
.scgrit-demo-shell > * { margin-top: 0; }
```

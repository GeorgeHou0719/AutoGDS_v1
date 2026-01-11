# Troubleshooting

## Empty `layout.gds`
- Check `layout_emit.json` for `component_call_failed` or missing dependencies.
- Verify that `blueprint.json` has parts and links.

## No Components Selected
- Check `topology_plan.json` to ensure nodes are created.
- Inspect `options_node_*.json` for candidate lists.

## Wrong Ports or Missing Links
- Review `blueprint.json` for `port_map_issues`.
- Ensure the prompt includes explicit port forms like `1x2` or `2x2`.

## Parameter Not Applied
- Confirm the parameter appears in `blueprint.json` under `params`.
- Use explicit units (`um`, `nm`) and standard names like `delta_length`.

## GDS Emission Errors
- Install layout extras: `pip install ".[layout]"`.
- Ensure `gdsfactory` imports correctly in your environment.


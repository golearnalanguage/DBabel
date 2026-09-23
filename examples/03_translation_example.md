# Synthetic translation example

Input contains:
- prose;
- a product name;
- a configuration key `EXAMPLE_MODE`;
- a filesystem path `/opt/example/config.ini`.

DBabel should protect the product name, configuration key, and path as appropriate, resolve high-risk terminology before MT, then validate the translated prose after MT/LLM output.

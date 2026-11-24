"""AI foundation: a provider-neutral interface, a registry of tools that call the app's own services, and the prompt.

The model never touches the database. It can only ask for a tool by name; the tool validates the arguments and calls the same service
functions the web pages use, scoped to the signed-in user. Tools that change data don't run until the user approves them."""

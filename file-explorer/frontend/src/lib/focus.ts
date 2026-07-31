/// Focus an input as soon as it appears, and select what is in it so typing
/// replaces the old name. The `autofocus` attribute is unreliable for elements
/// mounted after page load.
export function autofocus(node: HTMLInputElement) {
	node.focus();
	node.select();
}

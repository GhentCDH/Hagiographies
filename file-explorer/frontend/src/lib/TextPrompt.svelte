<script lang="ts">
	import { autofocus } from './focus';

	type Props = {
		title: string;
		label: string;
		confirmLabel?: string;
		onconfirm: (value: string) => void;
		oncancel: () => void;
	};
	let { title, label, confirmLabel = 'Save', onconfirm, oncancel }: Props = $props();

	let value = $state('');

	function submit(event: Event) {
		event.preventDefault();
		const trimmed = value.trim();
		if (trimmed) onconfirm(trimmed);
	}
</script>

<div
	class="fixed inset-0 z-20 flex items-center justify-center bg-stone-900/40 p-4"
	role="presentation"
	onclick={(e) => e.target === e.currentTarget && oncancel()}
>
	<form
		class="w-full max-w-md rounded-lg border border-stone-300 bg-white p-5 shadow-lg"
		onsubmit={submit}
	>
		<h2 class="text-base font-semibold text-stone-900">{title}</h2>

		<label class="mt-4 block text-sm text-stone-600" for="text-prompt-input">{label}</label>
		<input
			id="text-prompt-input"
			class="mt-1 w-full rounded border border-stone-300 px-2 py-1.5 text-sm focus:border-stone-500 focus:outline-none"
			bind:value
			use:autofocus
			onkeydown={(e) => e.key === 'Escape' && oncancel()}
		/>

		<div class="mt-5 flex justify-end gap-2">
			<button
				type="button"
				class="rounded px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
				onclick={oncancel}>Cancel</button
			>
			<button
				type="submit"
				class="rounded bg-stone-800 px-3 py-1.5 text-sm text-white hover:bg-stone-700 disabled:opacity-40"
				disabled={!value.trim()}>{confirmLabel}</button
			>
		</div>
	</form>
</div>

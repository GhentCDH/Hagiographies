<script lang="ts">
	type Props = {
		name:
			| 'upload'
			| 'pencil'
			| 'move'
			| 'link'
			| 'folder'
			| 'new-folder'
			| 'up'
			| 'check'
			| 'cancel'
			| 'folder-up'
			| 'search'
			| 'undo';
	};
	let { name }: Props = $props();
</script>

<svg
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.8"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	class="size-5"
>
	{#if name === 'upload'}
		<path d="M12 16V4m0 0L8 8m4-4 4 4" />
		<path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
	{:else if name === 'pencil'}
		<path d="M4 20h4l10-10a2.5 2.5 0 0 0-3.5-3.5L4.5 16.5 4 20Z" />
	{:else if name === 'move'}
		<path d="M3 7a2 2 0 0 1 2-2h3.5l1.5 2H15a2 2 0 0 1 2 2v3" />
		<path d="M3 7v10a2 2 0 0 0 2 2h6" />
		<path d="M15 16h6m0 0-2.5-2.5M21 16l-2.5 2.5" />
	{:else if name === 'link'}
		<path d="M10 13a4 4 0 0 0 5.66 0l2.5-2.5a4 4 0 0 0-5.66-5.66L11 6.34" />
		<path d="M14 11a4 4 0 0 0-5.66 0l-2.5 2.5a4 4 0 0 0 5.66 5.66L13 17.66" />
	{:else if name === 'folder'}
		<path d="M3 7a2 2 0 0 1 2-2h3.5l1.5 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
	{:else if name === 'new-folder'}
		<path d="M3 7a2 2 0 0 1 2-2h3.5l1.5 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
		<path d="M12 11v5m-2.5-2.5h5" />
	{:else if name === 'up'}
		<path d="M12 19V6m0 0-5 5m5-5 5 5" />
	{:else if name === 'check'}
		<path d="m5 13 4.5 4.5L19 7" />
	{:else if name === 'cancel'}
		<path d="M6 6l12 12M18 6L6 18" />
	{:else if name === 'search'}
		<circle cx="11" cy="11" r="6" />
		<path d="m20 20-4.5-4.5" />
	{:else if name === 'undo'}
		<path d="M4 9h11a5 5 0 0 1 0 10h-6" />
		<path d="M4 9l4-4M4 9l4 4" />
	{:else if name === 'folder-up'}
		<path d="M3 8a2 2 0 0 1 2-2h3.5l1.5 2H19a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8Z" />
		<path d="M12 18v-6m0 0-2.5 2.5M12 12l2.5 2.5" />
	{/if}
</svg>

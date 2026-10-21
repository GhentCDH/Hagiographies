<script lang="ts">
	import { folders as fetchFolders, type Folder } from './api';
	import Icon from './Icon.svelte';

	type Props = {
		title: string;
		/// Where the thing already is, so offering it would only confuse.
		disabled?: string;
		/// A folder cannot be moved into itself or anything below it.
		excludeSubtree?: string;
		/// Off for folders: nothing may be moved up to the top level.
		allowRoot?: boolean;
		onpick: (path: string) => void;
		oncancel: () => void;
	};
	let {
		title,
		disabled,
		excludeSubtree,
		allowRoot = true,
		onpick,
		oncancel
	}: Props = $props();

	let list = $state<Folder[] | null>(null);
	let error = $state<string | null>(null);

	fetchFolders()
		.then((f) => (list = f))
		.catch((e: Error) => (error = e.message));

	/// Why this folder cannot be picked, or null if it can.
	function refusal(folder: Folder): string | null {
		if (folder.path === disabled) return 'already here';
		if (!allowRoot && folder.path === '') return 'not the top level';
		if (
			excludeSubtree &&
			(folder.path === excludeSubtree || folder.path.startsWith(`${excludeSubtree}/`))
		) {
			return 'inside itself';
		}
		return null;
	}
</script>

<div
	class="fixed inset-0 z-20 flex items-center justify-center bg-stone-900/40 p-4"
	role="presentation"
	onclick={(e) => e.target === e.currentTarget && oncancel()}
>
	<div class="flex max-h-[80vh] w-full max-w-md flex-col rounded-lg border border-stone-300 bg-white shadow-lg">
		<h2 class="border-b border-stone-200 p-4 text-base font-semibold text-stone-900">{title}</h2>

		<div class="min-h-0 flex-1 overflow-y-auto p-2">
			{#if error}
				<p class="p-2 text-sm text-red-700">{error}</p>
			{:else if !list}
				<p class="p-2 text-sm text-stone-500">Loading folders...</p>
			{:else}
				{#each list as folder (folder.path)}
					{@const why = refusal(folder)}
					<button
						type="button"
						class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-stone-100 disabled:cursor-default disabled:text-stone-400 disabled:hover:bg-transparent"
						style="padding-left: {0.5 + folder.depth * 1.1}rem"
						disabled={why !== null}
						onclick={() => onpick(folder.path)}
					>
						<span class="text-stone-400"><Icon name="folder" /></span>
						<span class="truncate">{folder.name}</span>
						{#if why}
							<span class="text-xs text-stone-400">({why})</span>
						{/if}
					</button>
				{/each}
			{/if}
		</div>

		<div class="flex justify-end border-t border-stone-200 p-3">
			<button
				type="button"
				class="rounded px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
				onclick={oncancel}>Cancel</button
			>
		</div>
	</div>
</div>

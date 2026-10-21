<script lang="ts">
	import { innerPath, pickedFolderName } from './api';
	import { autofocus } from './focus';

	type Props = {
		dir: string;
		onupload: (files: File[], name: string) => void;
		oncancel: () => void;
	};
	let { dir, onupload, oncancel }: Props = $props();

	let files = $state<File[]>([]);
	let name = $state('');

	function pick(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		files = Array.from(input.files ?? []);
		// Prefill with the folder they picked; the files keep their own names.
		if (files.length) name = pickedFolderName(files);
	}

	function submit(event: Event) {
		event.preventDefault();
		const trimmed = name.trim();
		if (files.length && trimmed) onupload(files, trimmed);
	}

	const preview = $derived(files.slice(0, 5).map(innerPath));
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
		<h2 class="text-base font-semibold text-stone-900">Upload a folder</h2>
		<p class="mt-1 text-sm text-stone-500">
			It goes into <span class="font-mono">{dir || 'the share root'}</span>, keeping the structure
			inside it.
		</p>

		<label class="mt-4 block text-sm text-stone-600" for="upload-folder">Folder</label>
		<input
			id="upload-folder"
			type="file"
			webkitdirectory
			multiple
			class="mt-1 w-full text-sm file:mr-3 file:rounded file:border-0 file:bg-stone-800 file:px-3 file:py-1.5 file:text-white hover:file:bg-stone-700"
			onchange={pick}
		/>

		{#if files.length}
			<p class="mt-2 text-sm text-stone-600">
				{files.length} file{files.length === 1 ? '' : 's'}:
				<span class="text-stone-500">{preview.join(', ')}{files.length > 5 ? ', ...' : ''}</span>
			</p>
		{/if}

		<label class="mt-4 block text-sm text-stone-600" for="upload-folder-name">
			Name on the share
		</label>
		{#if files.length}
			<input
				id="upload-folder-name"
				class="mt-1 w-full rounded border border-stone-300 px-2 py-1.5 text-sm focus:border-stone-500 focus:outline-none"
				bind:value={name}
				use:autofocus
				onkeydown={(e) => e.key === 'Escape' && oncancel()}
			/>
		{:else}
			<input
				id="upload-folder-name"
				class="mt-1 w-full rounded border border-stone-300 px-2 py-1.5 text-sm"
				disabled
			/>
		{/if}

		<div class="mt-5 flex justify-end gap-2">
			<button
				type="button"
				class="rounded px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
				onclick={oncancel}>Cancel</button
			>
			<button
				type="submit"
				class="rounded bg-stone-800 px-3 py-1.5 text-sm text-white hover:bg-stone-700 disabled:opacity-40"
				disabled={!files.length || !name.trim()}>Upload folder</button
			>
		</div>
	</form>
</div>

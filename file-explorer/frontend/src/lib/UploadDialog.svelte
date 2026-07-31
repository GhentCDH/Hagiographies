<script lang="ts">
	type Props = {
		dir: string;
		onupload: (file: File, name: string) => void;
		oncancel: () => void;
	};
	let { dir, onupload, oncancel }: Props = $props();

	let file = $state<File | null>(null);
	let name = $state('');

	function pick(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
		// Prefill with the original name, which is usually the one they want.
		if (file) name = file.name;
	}

	function submit(event: Event) {
		event.preventDefault();
		const trimmed = name.trim();
		if (file && trimmed) onupload(file, trimmed);
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
		<h2 class="text-base font-semibold text-stone-900">Upload a file</h2>
		<p class="mt-1 text-sm text-stone-500">
			It goes into <span class="font-mono">{dir || 'the share root'}</span>.
		</p>

		<label class="mt-4 block text-sm text-stone-600" for="upload-file">File</label>
		<input
			id="upload-file"
			type="file"
			class="mt-1 w-full text-sm file:mr-3 file:rounded file:border-0 file:bg-stone-800 file:px-3 file:py-1.5 file:text-white hover:file:bg-stone-700"
			onchange={pick}
		/>

		<label class="mt-4 block text-sm text-stone-600" for="upload-name">Name on the share</label>
		<input
			id="upload-name"
			class="mt-1 w-full rounded border border-stone-300 px-2 py-1.5 text-sm focus:border-stone-500 focus:outline-none"
			bind:value={name}
			disabled={!file}
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
				disabled={!file || !name.trim()}>Upload</button
			>
		</div>
	</form>
</div>

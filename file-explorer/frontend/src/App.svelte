<script lang="ts">
	import {
		browse,
		createDir,
		moveDir,
		moveFile,
		renameDir,
		renameFile,
		search,
		undo,
		undoAvailable,
		upload,
		uploadFolder,
		type Listing,
		type SearchResults
	} from './lib/api';
	import { autofocus } from './lib/focus';
	import { fileSize, pathTail, shortDate } from './lib/format';
	import FolderPicker from './lib/FolderPicker.svelte';
	import Icon from './lib/Icon.svelte';
	import TextPrompt from './lib/TextPrompt.svelte';
	import UploadDialog from './lib/UploadDialog.svelte';
	import UploadFolderDialog from './lib/UploadFolderDialog.svelte';

	let path = $state(pathFromHash());
	let listing = $state<Listing | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);

	/// A file is addressed by its id, a folder by its path. `dir` is where it sits,
	/// so the move dialog can grey out the folder it is already in.
	type Target = { kind: 'file' | 'dir'; id: string; name: string; dir: string };

	let renaming = $state<Target | null>(null);
	/// What is in the rename box, separate from the name it started as.
	let newName = $state('');
	let moving = $state<Target | null>(null);
	let uploading = $state(false);
	let uploadingFolder = $state(false);
	let newFolder = $state(false);

	let query = $state('');
	let results = $state<SearchResults | null>(null);
	/// Guards against an earlier search answering after a later one.
	let searches = 0;

	let undoLabel = $state<string | null>(null);

	/// Which row shows the tick, and the message that floats over the page. The
	/// message is positioned fixed so confirming a copy never moves the table.
	let copied = $state<string | null>(null);
	let toast = $state<string | null>(null);
	/// Worth reading but not a failure, like files left out of a folder upload.
	let notice = $state<string | null>(null);

	const searching = $derived(query.trim().length > 0);

	function say(message: string) {
		toast = message;
		setTimeout(() => (toast = null), 2500);
	}

	function startRename(target: Target) {
		renaming = target;
		newName = target.name;
	}

	function submitRename() {
		const target = renaming;
		if (!target) return;
		const name = newName.trim();
		if (!name || name === target.name) {
			renaming = null;
			return;
		}
		act(() => (target.kind === 'file' ? renameFile(target.id, name) : renameDir(target.id, name)));
	}

	/// The directory lives in the hash, so a refresh keeps your place.
	function pathFromHash(): string {
		const raw = location.hash.replace(/^#\/?/, '');
		try {
			return decodeURIComponent(raw);
		} catch {
			return '';
		}
	}

	function go(to: string) {
		query = '';
		location.hash = to ? `#/${encodeURI(to)}` : '#/';
	}

	async function load() {
		try {
			listing = await browse(path);
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
		try {
			undoLabel = (await undoAvailable()).label;
		} catch {
			undoLabel = null;
		}
		if (searching) await runSearch();
	}

	async function runSearch() {
		const q = query.trim();
		const mine = ++searches;
		try {
			const found = await search(q);
			// A slower earlier search must not overwrite a newer one.
			if (mine === searches) results = found;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	/// Run an action, reload, then show whatever it complained about.
	async function act(action: () => Promise<unknown>) {
		if (busy) return;
		busy = true;

		let failure: string | null = null;
		try {
			await action();
		} catch (e) {
			failure = (e as Error).message;
		}

		busy = false;
		renaming = null;
		moving = null;
		uploading = false;
		uploadingFolder = false;
		newFolder = false;

		// The reload has to come first, because a half-done action still changed
		// the listing. Setting the error afterwards keeps load() from clearing it.
		await load();
		error = failure;
	}

	async function copyLink(fileId: string, link: string) {
		try {
			await navigator.clipboard.writeText(link);
			copied = fileId;
			say('Link copied. Paste it into Mathesar.');
			setTimeout(() => (copied = null), 2500);
		} catch {
			error = 'The browser would not let us copy. The link is on the file name.';
		}
	}

	/// Reports what went in and what was left out, since the user named only the
	/// folder and cannot see per file problems otherwise.
	async function sendFolder(files: File[], name: string) {
		notice = null;
		const result = await uploadFolder(path, name, files);

		const count = result.files_uploaded;
		say(`Uploaded ${count} file${count === 1 ? '' : 's'} into ${name}.`);
		if (result.skipped.length) {
			notice = `Left out of ${name}: ${result.skipped.join('; ')}`;
		}
	}

	$effect(() => {
		const onhash = () => {
			path = pathFromHash();
		};
		window.addEventListener('hashchange', onhash);
		return () => window.removeEventListener('hashchange', onhash);
	});

	// Reloads whenever the path changes, including the first render.
	$effect(() => {
		path;
		load();
	});

	// Debounced, so typing does not fire a query per keystroke.
	$effect(() => {
		const q = query.trim();
		if (!q) {
			results = null;
			searches++;
			return;
		}
		const timer = setTimeout(runSearch, 180);
		return () => clearTimeout(timer);
	});

	const parent = $derived(path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '');
</script>

<main class="mx-auto max-w-5xl p-6">
	<div class="flex items-center justify-between gap-4">
		<h1 class="shrink-0 text-xl font-semibold text-stone-900">Hagiographies Files</h1>

		<div class="flex w-full max-w-sm items-center gap-1 rounded border border-stone-300 bg-white px-2 py-1.5 focus-within:border-stone-500">
			<span class="shrink-0 text-stone-400"><Icon name="search" /></span>
			<input
				class="w-full text-sm focus:outline-none"
				placeholder="Search the whole share"
				aria-label="Search the whole share"
				bind:value={query}
				onkeydown={(e) => e.key === 'Escape' && (query = '')}
			/>
			{#if searching}
				<button
					class="shrink-0 rounded p-0.5 text-stone-500 hover:bg-stone-100"
					title="Clear the search"
					onclick={() => (query = '')}
				>
					<Icon name="cancel" />
				</button>
			{/if}
		</div>
	</div>

	<div class="mt-4 flex items-end justify-between gap-4">
		{#if searching}
			<p class="min-w-0 text-sm text-stone-600">
				{#if results}
					{results.hits.length}{results.truncated ? '+' : ''} match{results.hits.length === 1
						? ''
						: 'es'} across the share
				{:else}
					Searching...
				{/if}
			</p>
		{:else}
			<nav class="min-w-0 text-sm text-stone-600" aria-label="Current folder">
				<button class="hover:text-stone-900 hover:underline" onclick={() => go('')}>
					share root
				</button>
				{#each listing?.breadcrumbs ?? [] as crumb (crumb.path)}
					<span class="px-1 text-stone-400">/</span>
					<button class="hover:text-stone-900 hover:underline" onclick={() => go(crumb.path)}>
						{crumb.name}
					</button>
				{/each}
			</nav>
		{/if}

		<div class="flex shrink-0 items-center gap-1">
			<button
				class="flex items-center gap-1.5 rounded px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-100 disabled:text-stone-300 disabled:hover:bg-transparent"
				title={undoLabel ? `Undo ${undoLabel}` : 'Nothing to undo'}
				disabled={!undoLabel}
				onclick={() =>
					act(async () => {
						say((await undo()).done);
					})}
			>
				<Icon name="undo" /> Undo
			</button>

			{#if !searching}
				{#if listing && !listing.at_root}
					<button
						class="flex items-center gap-1.5 rounded px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
						title="Make a folder here"
						onclick={() => (newFolder = true)}
					>
						<Icon name="new-folder" /> New folder
					</button>
				{/if}
				<button
					class="flex items-center gap-1.5 rounded px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
					title="Upload a file into this folder"
					onclick={() => (uploading = true)}
				>
					<Icon name="upload" /> Upload
				</button>
				{#if listing && !listing.at_root}
					<button
						class="flex items-center gap-1.5 rounded px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
						title="Upload a whole folder into this folder"
						onclick={() => (uploadingFolder = true)}
					>
						<Icon name="folder-up" /> Upload folder
					</button>
				{/if}
			{/if}
		</div>
	</div>

	{#if error}
		<div class="mt-3 flex items-start justify-between gap-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
			<p class="min-w-0 break-words">{error}</p>
			<button class="shrink-0 text-red-600 hover:text-red-900" onclick={() => (error = null)}>
				Dismiss
			</button>
		</div>
	{/if}

	{#if notice}
		<div class="mt-3 flex items-start justify-between gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
			<p class="min-w-0 break-words">{notice}</p>
			<button class="shrink-0 text-amber-700 hover:text-amber-950" onclick={() => (notice = null)}>
				Dismiss
			</button>
		</div>
	{/if}

	<!-- table-fixed keeps the action columns put no matter how long a name is. -->
	<table class="mt-3 w-full table-fixed border border-stone-300 text-sm">
		<thead>
			<tr class="border-b border-stone-300 text-left text-stone-500">
				<th class="px-3 py-2 font-medium">file name</th>
				<th class="w-24 px-3 py-2 text-right font-medium">size</th>
				<th class="w-32 px-3 py-2 text-right font-medium">
					{searching ? 'folder' : 'changed'}
				</th>
				<th class="w-10"></th>
				<th class="w-10"></th>
				<th class="w-10"></th>
			</tr>
		</thead>
		<tbody>
			{#if searching}
				{#each results?.hits ?? [] as hit (hit.file_id)}
					{@const target = {
						kind: 'file' as const,
						id: hit.file_id,
						name: hit.name,
						dir: hit.dir
					}}
					<tr class="border-b border-stone-200 hover:bg-stone-50">
						<td class="px-3 py-1.5 break-words">
							{#if renaming && renaming.id === hit.file_id}
								{@render renameBox()}
							{:else}
								<a
									class="text-stone-800 hover:underline"
									class:text-stone-400={hit.missing}
									class:line-through={hit.missing}
									href={hit.link}
									target="_blank"
									rel="noreferrer">{hit.name}</a
								>
								{#if hit.missing}
									<span class="ml-2 text-xs text-amber-700">missing on the share</span>
								{/if}
							{/if}
						</td>

						<td class="px-3 py-1.5 text-right text-stone-500">
							{hit.missing || hit.size_bytes === null ? '' : fileSize(hit.size_bytes)}
						</td>
						<td class="px-3 py-1.5 text-right">
							<button
								class="max-w-full truncate text-stone-500 hover:text-stone-900 hover:underline"
								title="Go to {hit.dir || 'the share root'}"
								onclick={() => go(hit.dir)}
							>
								{pathTail(hit.dir)}
							</button>
						</td>

						<td class="px-1 py-1.5">
							<button
								class="rounded p-1 text-blue-600 hover:bg-blue-50 disabled:text-stone-300"
								title="Rename"
								disabled={hit.missing}
								onclick={() => startRename(target)}
							>
								<Icon name="pencil" />
							</button>
						</td>
						<td class="px-1 py-1.5">
							{#if !hit.missing}
								<button
									class="rounded p-1 text-stone-500 hover:bg-stone-100"
									title="Move to another folder"
									onclick={() => (moving = target)}
								>
									<Icon name="move" />
								</button>
							{/if}
						</td>
						<td class="px-1 py-1.5">{@render copyButton(hit.file_id, hit.link)}</td>
					</tr>
				{/each}

				{#if results && results.hits.length === 0}
					<tr>
						<td class="px-3 py-6 text-center text-stone-500" colspan="6">
							Nothing on the share matches "{query.trim()}".
						</td>
					</tr>
				{/if}
			{:else}
				{#if listing && !listing.at_root}
					<tr class="border-b border-stone-200 hover:bg-stone-50">
						<td class="px-3 py-1.5" colspan="6">
							<button class="flex items-center gap-2 text-stone-600" onclick={() => go(parent)}>
								<Icon name="up" /> ..
							</button>
						</td>
					</tr>
				{/if}

				{#each listing?.entries ?? [] as entry (entry.path)}
					{@const target = {
						kind: entry.kind,
						id: entry.kind === 'file' ? entry.file_id : entry.path,
						name: entry.name,
						dir: path
					}}
					<tr class="border-b border-stone-200 hover:bg-stone-50">
						<td class="px-3 py-1.5 break-words">
							{#if renaming && renaming.id === target.id}
								{@render renameBox()}
							{:else if entry.kind === 'dir'}
								<button
									class="flex items-start gap-2 text-left text-stone-800 hover:underline"
									onclick={() => go(entry.path)}
								>
									<span class="mt-0.5 shrink-0 text-stone-400"><Icon name="folder" /></span>
									{entry.name}
								</button>
							{:else}
								<a
									class="text-stone-800 hover:underline"
									class:text-stone-400={entry.missing}
									class:line-through={entry.missing}
									href={entry.link}
									target="_blank"
									rel="noreferrer">{entry.name}</a
								>
								{#if entry.missing}
									<span class="ml-2 text-xs text-amber-700">missing on the share</span>
								{/if}
							{/if}
						</td>

						<td class="px-3 py-1.5 text-right text-stone-500">
							{entry.kind === 'file' && !entry.missing ? fileSize(entry.size_bytes) : ''}
						</td>
						<td class="px-3 py-1.5 text-right text-stone-500">
							{entry.kind === 'file' ? shortDate(entry.modified) : ''}
						</td>

						<td class="px-1 py-1.5">
							<button
								class="rounded p-1 text-blue-600 hover:bg-blue-50 disabled:text-stone-300"
								title="Rename"
								disabled={entry.kind === 'file' && entry.missing}
								onclick={() => startRename(target)}
							>
								<Icon name="pencil" />
							</button>
						</td>

						<td class="px-1 py-1.5">
							{#if entry.kind === 'file' ? !entry.missing : entry.path.includes('/')}
								<button
									class="rounded p-1 text-stone-500 hover:bg-stone-100"
									title="Move to another folder"
									onclick={() => (moving = target)}
								>
									<Icon name="move" />
								</button>
							{/if}
						</td>

						<td class="px-1 py-1.5">
							{#if entry.kind === 'file'}
								{@render copyButton(entry.file_id, entry.link)}
							{/if}
						</td>
					</tr>
				{/each}

				{#if listing && listing.entries.length === 0}
					<tr>
						<td class="px-3 py-6 text-center text-stone-500" colspan="6">This folder is empty.</td>
					</tr>
				{/if}
			{/if}
		</tbody>
	</table>
</main>

{#snippet renameBox()}
	<!-- No blur-to-cancel: it would fire before the buttons' click and throw the
	     edit away just as you tried to confirm it. -->
	<form
		class="flex items-center gap-1"
		onsubmit={(e) => {
			e.preventDefault();
			submitRename();
		}}
	>
		<input
			class="w-full min-w-0 rounded border border-stone-400 px-1.5 py-0.5 text-sm focus:outline-none"
			bind:value={newName}
			use:autofocus
			onkeydown={(e) => e.key === 'Escape' && (renaming = null)}
		/>
		<button
			type="submit"
			class="shrink-0 rounded p-1 text-green-700 hover:bg-green-50 disabled:text-stone-300"
			title="Save this name"
			disabled={!newName.trim()}
		>
			<Icon name="check" />
		</button>
		<button
			type="button"
			class="shrink-0 rounded p-1 text-stone-500 hover:bg-stone-100"
			title="Cancel (or press Escape)"
			onclick={() => (renaming = null)}
		>
			<Icon name="cancel" />
		</button>
	</form>
{/snippet}

{#snippet copyButton(fileId: string, link: string)}
	<!-- Same sized icon either way, so confirming does not shift the row. -->
	<button
		class="rounded p-1 hover:bg-stone-100"
		class:text-stone-500={copied !== fileId}
		class:text-green-700={copied === fileId}
		title={copied === fileId ? 'Link copied' : 'Copy the link for Mathesar'}
		onclick={() => copyLink(fileId, link)}
	>
		<Icon name={copied === fileId ? 'check' : 'link'} />
	</button>
{/snippet}

<!-- Fixed and non-interactive, so showing it cannot move anything on the page. -->
{#if toast}
	<div
		class="pointer-events-none fixed bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-md bg-stone-800 px-3 py-2 text-sm text-white shadow-lg"
		role="status"
	>
		<Icon name="check" />
		{toast}
	</div>
{/if}

{#if moving}
	{@const target = moving}
	<FolderPicker
		title="Move {target.name} to"
		disabled={target.dir}
		excludeSubtree={target.kind === 'dir' ? target.id : undefined}
		allowRoot={target.kind === 'file'}
		onpick={(dest) =>
			act(() => (target.kind === 'file' ? moveFile(target.id, dest) : moveDir(target.id, dest)))}
		oncancel={() => (moving = null)}
	/>
{/if}

{#if uploading}
	<UploadDialog
		dir={path}
		onupload={(file, name) => act(() => upload(path, name, file))}
		oncancel={() => (uploading = false)}
	/>
{/if}

{#if uploadingFolder}
	<UploadFolderDialog
		dir={path}
		onupload={(files, name) => act(() => sendFolder(files, name))}
		oncancel={() => (uploadingFolder = false)}
	/>
{/if}

{#if newFolder}
	<TextPrompt
		title="New folder"
		label="Name"
		confirmLabel="Create"
		onconfirm={(name) => act(() => createDir(path, name))}
		oncancel={() => (newFolder = false)}
	/>
{/if}

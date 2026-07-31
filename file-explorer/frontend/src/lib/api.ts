export type Crumb = { name: string; path: string };

export type DirEntry = { kind: 'dir'; name: string; path: string };

export type FileEntry = {
	kind: 'file';
	name: string;
	path: string;
	file_id: string;
	link: string;
	size_bytes: number;
	modified: string | null;
	missing: boolean;
};

export type Entry = DirEntry | FileEntry;

export type Listing = {
	path: string;
	at_root: boolean;
	breadcrumbs: Crumb[];
	entries: Entry[];
};

export type Folder = { path: string; name: string; depth: number };

/// Throws with the server's own message, which is written to be shown as is.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (!response.ok) {
		let message = `${response.status} ${response.statusText}`;
		try {
			const body = await response.json();
			if (body?.error) message = body.error;
		} catch {
			// A non-JSON body means the error is not one of ours.
		}
		throw new Error(message);
	}
	return response.json() as Promise<T>;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
	return request<T>(path, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
}

export function browse(path: string): Promise<Listing> {
	return request<Listing>(`/api/browse?path=${encodeURIComponent(path)}`);
}

export function folders(): Promise<Folder[]> {
	return request<{ folders: Folder[] }>('/api/folders').then((r) => r.folders);
}

export function renameFile(fileId: string, name: string) {
	return postJson(`/api/files/${fileId}/rename`, { name });
}

export function moveFile(fileId: string, destDir: string) {
	return postJson(`/api/files/${fileId}/move`, { dest_dir: destDir });
}

export function createDir(parent: string, name: string) {
	return postJson('/api/dirs', { parent, name });
}

export function renameDir(path: string, name: string) {
	return postJson('/api/dirs/rename', { path, name });
}

export function moveDir(path: string, destDir: string) {
	return postJson('/api/dirs/move', { path, dest_dir: destDir });
}

export type FolderUpload = { files_uploaded: number; skipped: string[] };

/// Files keep their own names; only the folder is named. Each file's path inside
/// the folder rides along as its multipart filename.
export function uploadFolder(parent: string, name: string, files: File[]) {
	const form = new FormData();
	form.append('parent', parent);
	form.append('name', name);
	for (const file of files) {
		form.append('file', file, innerPath(file));
	}
	return request<FolderUpload>('/api/upload-folder', { method: 'POST', body: form });
}

/// A file's path relative to the chosen folder. The browser gives us
/// "chosen/sub/a.pdf"; the leading folder is replaced by the name the user typed,
/// so drop it here.
export function innerPath(file: File): string {
	const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
	if (!relative) return file.name;
	const cut = relative.indexOf('/');
	return cut === -1 ? relative : relative.slice(cut + 1);
}

/// The folder the user actually picked, for prefilling the name box.
export function pickedFolderName(files: File[]): string {
	const relative = (files[0] as (File & { webkitRelativePath?: string }) | undefined)
		?.webkitRelativePath;
	return relative?.split('/')[0] ?? '';
}

export function upload(dir: string, name: string, file: File) {
	// The backend reads this as a stream, so dir and name must come before the
	// file or it cannot know where the bytes are going.
	const form = new FormData();
	form.append('dir', dir);
	form.append('name', name);
	form.append('file', file);
	return request('/api/upload', { method: 'POST', body: form });
}

export type Hit = {
	file_id: string;
	name: string;
	path: string;
	dir: string;
	link: string;
	size_bytes: number | null;
	missing: boolean;
};

export type SearchResults = { query: string; hits: Hit[]; truncated: boolean };

export function search(q: string): Promise<SearchResults> {
	return request<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`);
}

export function undoAvailable(): Promise<{ label: string | null }> {
	return request<{ label: string | null }>('/api/undo');
}

export function undo(): Promise<{ done: string }> {
	return request<{ done: string }>('/api/undo', { method: 'POST' });
}

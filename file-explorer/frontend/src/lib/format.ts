const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'];

export function fileSize(bytes: number): string {
	if (bytes === 0) return '0 B';
	let value = bytes;
	let unit = 0;
	while (value >= 1000 && unit < UNITS.length - 1) {
		value /= 1000;
		unit += 1;
	}
	return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${UNITS[unit]}`;
}

export function shortDate(iso: string | null): string {
	if (!iso) return '';
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return '';
	return date.toLocaleDateString(undefined, {
		year: 'numeric',
		month: 'short',
		day: 'numeric'
	});
}

/// The tail of a path, for a narrow column. The end of a path says more about
/// where a file is than the start does, so keep that and drop the head.
export function pathTail(path: string, keep = 2): string {
	if (!path) return 'share root';
	const parts = path.split('/');
	if (parts.length <= keep) return path;
	return `.../${parts.slice(-keep).join('/')}`;
}

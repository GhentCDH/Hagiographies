import { svelte } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), svelte()],
	build: {
		outDir: 'dist',
		emptyOutDir: true
	},
	server: {
		// In dev this runs next to `cargo run`, which serves the API and /f.
		proxy: {
			'/api': 'http://localhost:3000',
			'/f': 'http://localhost:3000'
		}
	}
});

import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
	kit: {
		adapter: adapter({ fallback: 'index.html' }),
		paths: { base: '/demumumind', relative: false },
		alias: { $lib: 'src/lib' }
	}
};
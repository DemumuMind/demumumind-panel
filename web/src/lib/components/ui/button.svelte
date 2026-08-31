<script lang="ts">
	let { class: className = '', disabled = false, ...rest }: { class?: string; disabled?: boolean; [key: string]: any } = $props();
</script>

<button class="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition-colors bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed {className}" {disabled} {...rest}>
	<slot />
</button>
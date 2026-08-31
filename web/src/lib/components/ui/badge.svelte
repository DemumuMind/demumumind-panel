<script lang="ts">
	let { children, variant = 'default', class: className = '' }: { children?: import('svelte').Snippet; variant?: 'default' | 'success' | 'danger' | 'warning'; class?: string } = $props();

	const colors: Record<string, string> = {
		default: 'bg-zinc-700 text-zinc-200',
		success: 'bg-green-900/50 text-green-400',
		danger: 'bg-red-900/50 text-red-400',
		warning: 'bg-yellow-900/50 text-yellow-400'
	};
</script>

<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {colors[variant] || colors.default} {className}">
	{@render children?.()}
</span>
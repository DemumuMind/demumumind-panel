<script lang="ts">
	import Card from '$lib/components/ui/card.svelte';

	let {
		children,
		label,
		value
	}: { children?: import('svelte').Snippet; label: string; value: string | number } = $props();
</script>

<Card>
	<div class="text-(--text-muted) text-sm flex items-center gap-1.5">{@render children?.()}</div>
	<div class="text-2xl font-semibold text-(--text) mt-1 tabular-nums">{value}</div>
	<div class="text-xs text-(--text-faint)">{label}</div>
</Card>

<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		value = $bindable(''),
		class: className = '',
		...rest
	}: { value?: string; class?: string; [key: string]: any } = $props();
</script>

<input
	{...rest}
	bind:value
	class={cn(
		'w-full rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text) placeholder:text-(--text-faint) transition-all duration-150',
		'hover:border-(--border-strong) focus:outline-none focus:ring-2 focus:ring-(--accent)/40 focus:border-(--accent)',
		className
	)}
/>
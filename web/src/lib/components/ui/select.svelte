<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		value = $bindable(''),
		children,
		class: className = '',
		...rest
	}: { value?: string; children?: import('svelte').Snippet; class?: string; [key: string]: any } = $props();
</script>

<select
	{...rest}
	bind:value
	class={cn(
		'w-full rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text) transition-all duration-150',
		'hover:border-(--border-strong) focus:outline-none focus:ring-2 focus:ring-(--accent)/40 focus:border-(--accent)',
		className
	)}
>
	{@render children?.()}
</select>
<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		children,
		class: className = '',
		hover = false,
		padded = true,
		...rest
	}: { children?: import('svelte').Snippet; class?: string; hover?: boolean; padded?: boolean; [key: string]: any } = $props();
</script>

<div
	class={cn(
		'rounded-xl border border-(--border) bg-(--bg-card) shadow-(--shadow-card)',
		padded && 'p-4',
		hover && 'hover:border-(--border-strong) hover:shadow-(--shadow-lift) hover:-translate-y-px',
		className
	)}
	{...rest}
>
	{@render children?.()}
</div>

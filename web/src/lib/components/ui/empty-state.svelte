<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		icon,
		title,
		description,
		action,
		class: className = ''
	}: { icon?: any; title: string; description?: string; action?: import('svelte').Snippet; class?: string } = $props();
</script>

<div class={cn('flex flex-col items-center justify-center gap-3 py-10 text-center', className)}>
	{#if icon}
		<div class="w-10 h-10 rounded-xl bg-(--bg-elevated) border border-(--border) flex items-center justify-center text-(--text-muted)">
			{@render icon()}
		</div>
	{/if}
	<div class="font-medium text-(--text)">{title}</div>
	{#if description}
		<div class="text-sm text-(--text-faint) max-w-sm">{description}</div>
	{/if}
	{#if action}
		<div class="mt-1">{@render action()}</div>
	{/if}
</div>

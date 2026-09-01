<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		children,
		variant = 'default',
		dot = false,
		class: className = ''
	}: {
		children?: import('svelte').Snippet;
		variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' | 'accent';
		dot?: boolean;
		class?: string;
	} = $props();

	const colors: Record<string, string> = {
		default: 'bg-(--bg-hover) text-(--text-muted) border border-(--border)',
		success: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
		danger: 'bg-red-500/10 text-red-400 border border-red-500/20',
		warning: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
		info: 'bg-sky-500/10 text-sky-400 border border-sky-500/20',
		accent: 'bg-(--accent-soft) text-(--accent-hover) border border-(--accent)/30'
	};

	const dots: Record<string, string> = {
		default: 'bg-(--text-faint)',
		success: 'bg-emerald-400',
		danger: 'bg-red-400',
		warning: 'bg-amber-400',
		info: 'bg-sky-400',
		accent: 'bg-(--accent)'
	};
</script>

<span class={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium', colors[variant] || colors.default, className)}>
	{#if dot}
		<span class={cn('w-1.5 h-1.5 rounded-full', dots[variant] || dots.default)}></span>
	{/if}
	{@render children?.()}
</span>

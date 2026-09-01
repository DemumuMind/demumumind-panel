<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		children,
		variant = 'primary',
		size = 'md',
		class: className = '',
		disabled = false,
		...rest
	}: {
		children?: import('svelte').Snippet;
		variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline';
		size?: 'sm' | 'md';
		class?: string;
		disabled?: boolean;
		[key: string]: any;
	} = $props();

	const base =
		'inline-flex items-center justify-center gap-1.5 font-medium rounded-lg transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--accent) disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 active:translate-y-px';

	const variants: Record<string, string> = {
		primary:
			'text-white shadow-(--shadow-card) bg-gradient-to-b from-(--accent) to-(--accent-2) hover:from-(--accent-hover) hover:to-(--accent) hover:-translate-y-px',
		secondary:
			'text-(--text) border border-(--border) bg-(--bg-elevated) hover:bg-(--bg-hover) hover:border-(--border-strong)',
		ghost: 'text-(--text-muted) hover:text-(--text) hover:bg-(--bg-hover)',
		danger:
			'text-white bg-gradient-to-b from-(--danger) to-red-600 hover:from-red-400 hover:to-red-600 hover:-translate-y-px',
		outline:
			'text-(--text) border border-(--accent) text-(--accent-hover) hover:bg-(--accent-soft)'
	};

	const sizes: Record<string, string> = {
		sm: 'text-xs px-2.5 py-1.5',
		md: 'text-sm px-4 py-2'
	};
</script>

<button class={cn(base, variants[variant], sizes[size], className)} {disabled} {...rest}>
	{@render children?.()}
</button>

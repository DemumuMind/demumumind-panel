<script lang="ts">
	let { children, class: className = '', ...rest }: { children?: import('svelte').Snippet; class?: string; [key: string]: any } = $props();
</script>

<div class="rounded-xl border border-zinc-800 bg-[#1a1a1e] p-4 {className}" {...rest}>
	{@render children?.()}
</div>
<script lang="ts">
	let { class: className = '', ...rest }: { class?: string; [key: string]: any } = $props();
</script>

<div class="rounded-xl border border-zinc-800 bg-[#1a1a1e] p-4 {className}" {...rest}>
	<slot />
</div>
<script lang="ts">
	let { value = $bindable(''), class: className = '', ...rest }: { value?: string; class?: string; [key: string]: any } = $props();
</script>

<input
	{...rest}
	bind:value
	class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 {className}"
/>
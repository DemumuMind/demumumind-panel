<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		children,
		headers,
		class: className = '',
		emptyText = 'No data',
		empty = false
	}: {
		children?: import('svelte').Snippet;
		headers: string[];
		class?: string;
		emptyText?: string;
		empty?: boolean;
	} = $props();
</script>

<div class="overflow-x-auto">
	<table class={cn('w-full text-sm', className)}>
		<thead>
			<tr class="text-left text-(--text-muted) border-b border-(--border)">
				{#each headers as h}
					<th class="py-2.5 px-3 font-medium text-xs uppercase tracking-wider">{h}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{@render children?.()}
			{#if empty}
				<tr>
					<td colspan={headers.length} class="py-8 text-center text-(--text-faint)">
						{emptyText}
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>

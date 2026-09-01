<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchImageGenerations, fetchImageGenerationBlob } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Image, RefreshCw } from 'lucide-svelte';

	let items = $state<any[]>([]);
	let total = $state(0);
	let page = $state(0);
	let loading = $state(false);
	let urls = $state<Record<string, string>>({});
	const pageSize = 24;

	async function load() {
		loading = true;
		try {
			const data = await fetchImageGenerations(pageSize, page * pageSize);
			items = data.items;
			total = data.total;
			// revoke old blob URLs to avoid leaks
			for (const k of Object.keys(urls)) URL.revokeObjectURL(urls[k]);
			urls = {};
			// eager-load first page images
			await Promise.all(
				data.items.slice(0, 12).map(async (g) => {
					try {
						urls[g.id] = await fetchImageGenerationBlob(g.id);
					} catch (e: any) {
						urls[g.id] = '';
					}
				})
			);
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function srcOf(g: any) {
		return urls[g.id] || '';
	}

	function pageUp() {
		if ((page + 1) * pageSize < total) {
			page += 1;
			load();
		}
	}

	function pageDown() {
		if (page > 0) {
			page -= 1;
			load();
		}
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Image class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Images</h1>
	{#if loading}
		<RefreshCw class="w-4 h-4 animate-spin text-(--text-faint)" />
	{/if}
</div>

<p class="text-sm text-(--text-muted) mb-4">Generated images — {total}</p>

{#if items.length === 0}
	<Card>
		<EmptyState title="No images generated yet" description="Generate an image via /v1/images/generations or an image model and it will appear here.">
			{#snippet icon()}<Image class="w-5 h-5" />{/snippet}
		</EmptyState>
	</Card>
{:else}
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
		{#each items as g}
			<Card class="overflow-hidden">
				{#if srcOf(g)}
					<a href={srcOf(g)} target="_blank" rel="noopener">
						<img
							src={srcOf(g)}
							alt={g.prompt}
							loading="lazy"
							class="w-full aspect-square object-cover bg-(--bg-elevated) hover:opacity-90 transition-opacity"
						/>
					</a>
				{:else}
					<div class="w-full aspect-square bg-(--bg-elevated) flex items-center justify-center text-(--text-faint)">
						<Image class="w-8 h-8" />
					</div>
				{/if}
				<div class="p-3">
					<p class="text-sm text-(--text) line-clamp-2 min-h-10">{g.prompt}</p>
					<div class="flex items-center gap-2 mt-2 text-xs text-(--text-faint)">
						{#if g.provider}
							<Badge variant="accent">{g.provider}</Badge>
						{/if}
						{#if g.model}
							<Badge variant="default">{g.model}</Badge>
						{/if}
						<span class="ml-auto tabular-nums">{new Date(g.created_at).toLocaleString()}</span>
					</div>
				</div>
			</Card>
		{/each}
	</div>

	<div class="flex items-center justify-between mt-4">
		<span class="text-xs text-(--text-faint)">Page {page + 1} · {total} total</span>
		<div class="flex gap-2">
			<button
				onclick={pageDown}
				disabled={page === 0}
				class="rounded-md border border-(--border) bg-(--bg-elevated) px-3 py-1.5 text-xs text-(--text-muted) hover:text-(--text) disabled:opacity-40"
			>← Prev</button>
			<button
				onclick={pageUp}
				disabled={(page + 1) * pageSize >= total}
				class="rounded-md border border-(--border) bg-(--bg-elevated) px-3 py-1.5 text-xs text-(--text-muted) hover:text-(--text) disabled:opacity-40"
			>Next →</button>
		</div>
	</div>
{/if}
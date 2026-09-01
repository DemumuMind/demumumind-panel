<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import Table from '$lib/components/ui/table.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchProviders, fetchModels, createModel, deleteModel, updateModelPricing } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Boxes, Plus, Trash2, Pencil, Sparkles, X } from 'lucide-svelte';

	let providers = $state<any[]>([]);
	let models = $state<any[]>([]);
	let providerId = $state('');
	let userModelId = $state('');
	let internalModel = $state('');
	let filterProvider = $state('');
	let filterText = $state('');

	// pricing modal state
	let editingModel = $state<any>(null);
	let editPrompt = $state('0');
	let editCompletion = $state('0');
	let editRequest = $state('0');
	let editFree = $state(false);
	let editRpm = $state('');
	let editRpd = $state('');

	async function load() {
		try {
			const pr = await fetchProviders(100, 0);
			providers = pr.items;
			if (!providerId && providers.length) providerId = providers[0].id;
			const mo = await fetchModels(1000, 0, filterProvider || undefined);
			models = mo.items;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	onMount(load);

	async function add() {
		try {
			await createModel({ provider_id: providerId, user_model_id: userModelId, internal_model: internalModel, is_active: true });
			showToast('Model mapped', 'success');
			userModelId = internalModel = '';
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function remove(id: string) {
		try {
			await deleteModel(id);
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	function openPricing(m: any) {
		editingModel = m;
		const meta = m.metadata || {};
		const p = meta.pricing || {};
		editPrompt = String(p.prompt ?? '0');
		editCompletion = String(p.completion ?? '0');
		editRequest = String(p.request ?? '0');
		editFree = meta.free ?? false;
		const limits = meta.limits || {};
		editRpm = String(limits.requests_per_minute ?? '');
		editRpd = String(limits.requests_per_day ?? '');
	}

	async function savePricing() {
		if (!editingModel) return;
		try {
			const data: any = {
				price_prompt_per_token: parseFloat(editPrompt) || 0,
				price_completion_per_token: parseFloat(editCompletion) || 0,
				price_request: parseFloat(editRequest) || 0,
				free: editFree
			};
			if (editRpm) data.limit_requests_per_minute = parseInt(editRpm, 10);
			if (editRpd) data.limit_requests_per_day = parseInt(editRpd, 10);
			await updateModelPricing(editingModel.id, data);
			showToast('Pricing updated', 'success');
			editingModel = null;
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	let visibleModels = $derived(
		models.filter((m) => {
			if (filterText && !m.user_model_id.toLowerCase().includes(filterText.toLowerCase())) return false;
			return true;
		})
	);

	function isFree(m: any): boolean {
		return m.metadata?.free === true;
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Boxes class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Models</h1>
</div>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3 text-(--text)">Map user model → internal model</h2>
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
		<Input placeholder="user_model_id (e.g. my-sonnet)" bind:value={userModelId} />
		<Input placeholder="internal model (e.g. claude-3-5-sonnet)" bind:value={internalModel} />
		<Select bind:value={providerId}>
			{#each providers as p}
				<option value={p.id}>{p.name}</option>
			{/each}
		</Select>
	</div>
	<Button onclick={add} disabled={!userModelId || !internalModel} class="mt-3"><Plus class="w-4 h-4" /> Map</Button>
</Card>

<Card>
	<div class="flex gap-2 mb-3 items-end">
		<div class="flex-1">
			<label class="text-xs text-(--text-muted) block mb-1">Filter by provider</label>
			<Select bind:value={filterProvider} onchange={() => load()}>
				<option value="">All providers</option>
				{#each providers as p}
					<option value={p.id}>{p.name}</option>
				{/each}
			</Select>
		</div>
		<div class="flex-1">
			<label class="text-xs text-(--text-muted) block mb-1">Search model</label>
			<Input placeholder="Search by name…" bind:value={filterText} />
		</div>
	</div>
	<Table headers={['user_model_id', 'internal_model', 'Pricing', 'Provider', 'Actions']}>
		{#each visibleModels as m}
			<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover) transition-colors">
				<td class="py-2 px-3 font-medium text-(--text)">{m.user_model_id}</td>
				<td class="py-2 px-3 text-(--text-muted)">{m.internal_model}</td>
				<td class="py-2 px-3">
					{#if isFree(m)}
						<Badge variant="success" dot>Free</Badge>
					{:else if m.metadata?.pricing?.prompt}
						<span class="text-xs tabular-nums text-(--text-muted)">
							${m.metadata.pricing.prompt}/{m.metadata.pricing.completion}
						</span>
					{:else}
						<span class="text-xs text-(--text-faint)">—</span>
					{/if}
				</td>
				<td class="py-2 px-3 text-(--text-muted)">{providers.find((p) => p.id === m.provider_id)?.name ?? m.provider_id.slice(0, 8)}</td>
				<td class="py-2 px-3 text-right flex gap-1 justify-end">
					<Button variant="ghost" size="sm" onclick={() => openPricing(m)}><Pencil class="w-3.5 h-3.5" /></Button>
					<Button variant="ghost" size="sm" onclick={() => remove(m.id)}><Trash2 class="w-3.5 h-3.5" /></Button>
				</td>
			</tr>
		{/each}
	</Table>
	{#if visibleModels.length === 0}
		<EmptyState title="No models mapped" description="Map a user model to a provider model.">
			{#snippet icon()}<Boxes class="w-5 h-5" />{/snippet}
		</EmptyState>
	{/if}
</Card>

<!-- Pricing modal -->
{#if editingModel}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => editingModel = null}>
		<div class="bg-(--bg) rounded-xl border border-(--border) p-6 w-full max-w-md shadow-2xl" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-lg font-semibold text-(--text)">Pricing: {editingModel.user_model_id}</h3>
				<button onclick={() => editingModel = null} class="text-(--text-muted) hover:text-(--text)"><X class="w-5 h-5" /></button>
			</div>
			<div class="space-y-3">
				<div class="grid grid-cols-3 gap-2">
					<div>
						<label class="text-xs text-(--text-muted) block mb-1">Prompt $/token</label>
						<Input type="number" step="any" bind:value={editPrompt} />
					</div>
					<div>
						<label class="text-xs text-(--text-muted) block mb-1">Completion $/token</label>
						<Input type="number" step="any" bind:value={editCompletion} />
					</div>
					<div>
						<label class="text-xs text-(--text-muted) block mb-1">Request $</label>
						<Input type="number" step="any" bind:value={editRequest} />
					</div>
				</div>
				<div class="flex items-center gap-2">
					<input type="checkbox" id="free-check" bind:checked={editFree} class="rounded border-(--border) accent-(--accent)" />
					<label for="free-check" class="text-sm text-(--text)">Free / Unlimited</label>
				</div>
				<div class="grid grid-cols-2 gap-2">
					<div>
						<label class="text-xs text-(--text-muted) block mb-1">Limit requests/min</label>
						<Input type="number" step="1" placeholder="e.g. 20" bind:value={editRpm} />
					</div>
					<div>
						<label class="text-xs text-(--text-muted) block mb-1">Limit requests/day</label>
						<Input type="number" step="1" placeholder="e.g. 200" bind:value={editRpd} />
					</div>
				</div>
				<Button onclick={savePricing} class="w-full mt-2"><Sparkles class="w-4 h-4" /> Save Pricing</Button>
			</div>
		</div>
	</div>
{/if}
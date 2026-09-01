<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Table from '$lib/components/ui/table.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchProviders, fetchModels, createModel, deleteModel } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Boxes, Plus, Trash2 } from 'lucide-svelte';

	let providers = $state<any[]>([]);
	let models = $state<any[]>([]);
	let providerId = $state('');
	let userModelId = $state('');
	let internalModel = $state('');

	async function load() {
		try {
			const [pr, mo] = await Promise.all([fetchProviders(100, 0), fetchModels(100, 0)]);
			providers = pr.items;
			models = mo.items;
			if (!providerId && providers.length) providerId = providers[0].id;
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
	<Table headers={['user_model_id', 'internal_model', 'Provider', 'Actions']}>
		{#each models as m}
			<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover) transition-colors">
				<td class="py-2 px-3 font-medium text-(--text)">{m.user_model_id}</td>
				<td class="py-2 px-3 text-(--text-muted)">{m.internal_model}</td>
				<td class="py-2 px-3 text-(--text-muted)">{providers.find((p) => p.id === m.provider_id)?.name ?? m.provider_id.slice(0, 8)}</td>
				<td class="py-2 px-3 text-right">
					<Button variant="ghost" size="sm" onclick={() => remove(m.id)}><Trash2 class="w-3.5 h-3.5" /></Button>
				</td>
			</tr>
		{/each}
	</Table>
	{#if models.length === 0}
		<EmptyState title="No models mapped" description="Map a user model to a provider model.">
			{#snippet icon()}<Boxes class="w-5 h-5" />{/snippet}
		</EmptyState>
	{/if}
</Card>

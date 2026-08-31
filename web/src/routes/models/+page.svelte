<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import { fetchProviders, fetchModels, createModel, deleteModel } from '$lib/api';
	import { showToast } from '$lib/stores';

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

<h1 class="text-2xl font-bold mb-6">Models</h1>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3">Map user model → internal model</h2>
	<div class="grid grid-cols-4 gap-3">
		<Input placeholder="user_model_id (e.g. my-sonnet)" bind:value={userModelId} />
		<Input placeholder="internal model (e.g. claude-3-5-sonnet)" bind:value={internalModel} />
		<Select bind:value={providerId}>
			{#each providers as p}
				<option value={p.id}>{p.name}</option>
			{/each}
		</Select>
	</div>
	<Button onclick={add} disabled={!userModelId || !internalModel} class="mt-3">Map</Button>
</Card>

<Card>
	<table class="w-full text-sm">
		<thead>
			<tr class="text-left text-zinc-400 border-b border-zinc-800">
				<th class="py-2">user_model_id</th>
				<th>internal_model</th>
				<th>Provider</th>
				<th class="text-right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each models as m}
				<tr class="border-b border-zinc-800/50">
					<td class="py-2 font-medium">{m.user_model_id}</td>
					<td class="text-zinc-400">{m.internal_model}</td>
					<td>{providers.find((p) => p.id === m.provider_id)?.name ?? m.provider_id.slice(0, 8)}</td>
					<td class="text-right">
						<button onclick={() => remove(m.id)} class="text-xs text-red-400 hover:text-red-300">Delete</button>
					</td>
				</tr>
			{/each}
			{#if models.length === 0}
				<tr><td colspan="4" class="py-4 text-center text-zinc-500">No models mapped</td></tr>
			{/if}
		</tbody>
	</table>
</Card>
import { app } from '../../scripts/app.js'
import { repairPrimitiveWriterInputs } from './primitive-inputs.js'

const INSTALLED = Symbol.for('PromptHelper.PrimitiveInputs')

app.registerExtension({
  name: 'PromptHelper.PrimitiveInputs',
  setup() {
    const original = app.graphToPrompt
    if (original[INSTALLED]) return
    const wrapped = async function (...args) {
      const result = await original.apply(this, args)
      repairPrimitiveWriterInputs(result?.workflow, result?.output)
      return result
    }
    wrapped[INSTALLED] = true
    app.graphToPrompt = wrapped
  },
})
